import tlc

import ultralytics
from ultralytics.models.yolo.model import YOLO
from ultralytics.utils.tlc.detect.nn import TLCDetectionModel
from ultralytics.utils.tlc.detect.trainer import TLCDetectionTrainer
from ultralytics.utils.tlc.detect.utils import tlc_check_dataset
from ultralytics.utils.tlc.detect.validator import TLCDetectionValidator


def check_det_dataset(data: str):
    """Check if the dataset is compatible with the 3LC."""
    tables = tlc_check_dataset(data)
    names = tables["train"].get_value_map_for_column(tlc.BOUNDING_BOXES)
    return {
        "train": tables["train"],
        "val": tables["val"],
        "nc": len(names),
        "names": names, }


ultralytics.engine.validator.check_det_dataset = check_det_dataset


class TLCYOLO(YOLO):
    """ YOLO (You Only Look Once) object detection model with 3LC integration. """

    @property
    def task_map(self):
        """ Map head to 3LC model, trainer, validator, and predictor classes. """
        task_map = super().task_map
        task_map["detect"]["model"] = TLCDetectionModel
        task_map["detect"]["trainer"] = TLCDetectionTrainer
        task_map["detect"]["validator"] = TLCDetectionValidator

        return task_map
