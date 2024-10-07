# Ultralytics YOLO 🚀, AGPL-3.0 license
"""Functions for estimating the best YOLO batch size to use a fraction of the available CUDA memory in PyTorch."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

from ultralytics.utils import DEFAULT_CFG, LOGGER, colorstr
from ultralytics.utils.torch_utils import profile


def check_train_batch_size(model, imgsz=640, amp=True, batch=-1):
    """
    Compute optimal YOLO training batch size by running autobatch in a separate process.

    Args:
        model (torch.nn.Module): YOLO model to check batch size for.
        imgsz (int, optional): Image size used for training. Defaults to 640.
        amp (bool, optional): Use automatic mixed precision if True. Defaults to True.
        batch (float, optional): Fraction of GPU memory to use. If -1, use default. Defaults to -1.

    Returns:
        (int): Optimal batch size computed using the autobatch() function.
    """
    prefix = colorstr("AutoBatch: ")
    LOGGER.info(f"{prefix}Computing optimal batch size for imgsz={imgsz}")

    device = next(model.parameters()).device
    if device.type in {"cpu", "mps"}:
        LOGGER.info(f"{prefix}⚠️ CUDA not detected, using default CPU batch-size {DEFAULT_CFG.batch}")
        return DEFAULT_CFG.batch

    fraction = batch if 0.0 < batch < 1.0 else 0.60

    try:
        # Save model to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp_file:
            torch.save(model, tmp_file.name)
            tmp_file_path = Path(tmp_file.name)

        # Prepare the Python code to be executed in the subprocess
        code = f"""
import torch
from ultralytics.utils.autobatch import autobatch
import json

try:
    model = torch.load('{tmp_file_path}', map_location='{device}')
    batch_size = autobatch(model, imgsz={imgsz}, fraction={fraction}, amp={amp})
    print(json.dumps({{"batch_size": int(batch_size)}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""

        # Run the code as a separate process
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

        # Parse the output
        try:
            output = json.loads(result.stdout)
            if "error" in output:
                raise RuntimeError(output["error"])
            batch_size = output["batch_size"]
            LOGGER.info(f"{prefix}Determined optimal batch size: {batch_size}")
            return batch_size
        except json.JSONDecodeError:
            LOGGER.error(f"{prefix}Failed to parse subprocess output. stdout: {result.stdout}, stderr: {result.stderr}")
            raise

    except subprocess.CalledProcessError as e:
        LOGGER.warning(f"{prefix}WARNING ⚠️ Subprocess error: {e}")
        LOGGER.warning(f"{prefix}Subprocess stdout: {e.stdout}")
        LOGGER.warning(f"{prefix}Subprocess stderr: {e.stderr}")
    except Exception as e:
        LOGGER.warning(f"{prefix}WARNING ⚠️ Error: {str(e)}")
        LOGGER.warning(f"{prefix}Using default batch-size {DEFAULT_CFG.batch}")
        return DEFAULT_CFG.batch

    finally:
        # Delete the temporary file
        tmp_file_path.unlink(missing_ok=True)
        torch.cuda.empty_cache()


def autobatch(model, imgsz=640, fraction=0.60, batch_size=DEFAULT_CFG.batch):
    """
    Automatically estimate the best YOLO batch size to use a fraction of the available CUDA memory.

    Args:
        model (torch.nn.module): YOLO model to compute batch size for.
        imgsz (int, optional): The image size used as input for the YOLO model. Defaults to 640.
        fraction (float, optional): The fraction of available CUDA memory to use. Defaults to 0.60.
        batch_size (int, optional): The default batch size to use if an error is detected. Defaults to 16.

    Returns:
        (int): The optimal batch size.
    """
    # Check device
    prefix = colorstr("AutoBatch: ")
    LOGGER.info(f"{prefix}Computing optimal batch size for imgsz={imgsz} at {fraction * 100}% CUDA memory utilization.")
    device = next(model.parameters()).device  # get model device
    if device.type in {"cpu", "mps"}:
        LOGGER.info(f"{prefix} ⚠️ intended for CUDA devices, using default batch-size {batch_size}")
        return batch_size
    if torch.backends.cudnn.benchmark:
        LOGGER.info(f"{prefix} ⚠️ Requires torch.backends.cudnn.benchmark=False, using default batch-size {batch_size}")
        return batch_size

    # Inspect CUDA memory
    gb = 1 << 30  # bytes to GiB (1024 ** 3)
    d = str(device).upper()  # 'CUDA:0'
    properties = torch.cuda.get_device_properties(device)  # device properties
    t = properties.total_memory / gb  # GiB total
    r = torch.cuda.memory_reserved(device) / gb  # GiB reserved
    a = torch.cuda.memory_allocated(device) / gb  # GiB allocated
    f = t - (r + a)  # GiB free
    LOGGER.info(f"{prefix}{d} ({properties.name}) {t:.2f}G total, {r:.2f}G reserved, {a:.2f}G allocated, {f:.2f}G free")

    # Profile batch sizes
    batch_sizes = [1, 2, 4, 8, 16]
    try:
        img = [torch.empty(b, 3, imgsz, imgsz) for b in batch_sizes]
        results = profile(img, model, n=3, device=device)

        # Fit a solution
        y = [x[2] for x in results if x]  # memory [2]
        p = np.polyfit(batch_sizes[: len(y)], y, deg=1)  # first degree polynomial fit
        b = int((f * fraction - p[1]) / p[0])  # y intercept (optimal batch size)
        if None in results:  # some sizes failed
            i = results.index(None)  # first fail index
            if b >= batch_sizes[i]:  # y intercept above failure point
                b = batch_sizes[max(i - 1, 0)]  # select prior safe point
        if b < 1 or b > 1024:  # b outside of safe range
            b = batch_size
            LOGGER.info(f"{prefix}WARNING ⚠️ CUDA anomaly detected, using default batch-size {batch_size}.")

        fraction = (np.polyval(p, b) + r + a) / t  # actual fraction predicted
        LOGGER.info(f"{prefix}Using batch-size {b} for {d} {t * fraction:.2f}G/{t:.2f}G ({fraction * 100:.0f}%) ✅")
        return b
    except Exception as e:
        LOGGER.warning(f"{prefix}WARNING ⚠️ error detected: {e},  using default batch-size {batch_size}.")
        return batch_size
