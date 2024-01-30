import copy
import tlc
import ultralytics

from ultralytics.data import build_dataloader
from ultralytics.models.yolo.detect import DetectionTrainer
from ultralytics.utils import (
    DEFAULT_CFG, LOGGER, RANK)
from ultralytics.utils.tlc.detect.validator import TLCDetectionValidator
from ultralytics.utils.tlc.detect.nn import TLCDetectionModel
from ultralytics.utils.torch_utils import de_parallel
from ultralytics.utils.tlc.detect.dataset import build_tlc_dataset
from ultralytics.utils.tlc.detect.utils import parse_environment_variables, get_metrics_collection_epochs, tlc_check_dataset
from ultralytics.utils.torch_utils import torch_distributed_zero_first


def check_det_dataset(data: str):
    """Check if the dataset is compatible with the 3LC."""
    tables = tlc_check_dataset(data)
    names = tables["train"].get_value_map_for_column(tlc.BOUNDING_BOXES)
    return {
        "train": tables["train"],
        "val": tables["val"],
        "nc": len(names),
        "names": names,
    }

ultralytics.engine.trainer.check_det_dataset = check_det_dataset

class TLCDetectionTrainer(DetectionTrainer):
    """A class extending the BaseTrainer class for training a detection model using the 3LC."""

    def __init__(self, cfg=DEFAULT_CFG, overrides=None, _callbacks=None):
        LOGGER.info("Using 3LC Trainer 🌟")
        super().__init__(cfg, overrides, _callbacks)
        self._train_validator = None
        self._env_vars = parse_environment_variables()
        self._collection_epochs = get_metrics_collection_epochs(
                self._env_vars['COLLECTION_EPOCH_START'],
                self.args.epochs,
                self._env_vars['COLLECTION_EPOCH_INTERVAL'],
                self._env_vars['COLLECTION_DISABLE']
            )

        self._run = None

        if not self._env_vars['COLLECTION_DISABLE']:        
            self._run = tlc.init(project_name=self.data["train"].project_name)

    @property
    def train_validator(self):
        if not self._train_validator:
            if RANK in (-1,0):
                train_val_loader = self.get_dataloader(
                    self.testset, batch_size=self.batch_size if self.args.task == "obb" else self.batch_size * 2, rank=-1, mode="val", split="train",
                )
                self._train_validator = self.get_validator(loader=train_val_loader)
        return self._train_validator

    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train", split="val"):
        """Construct and return dataloader."""
        assert mode in ["train", "val"]
        with torch_distributed_zero_first(rank):  # init dataset *.cache only once if DDP
            dataset = self.build_dataset(dataset_path, mode, batch_size, split=split)
        shuffle = mode == "train"
        if getattr(dataset, "rect", False) and shuffle:
            LOGGER.warning("WARNING ⚠️ 'rect=True' is incompatible with DataLoader shuffle, setting shuffle=False")
            shuffle = False
        workers = self.args.workers if mode == "train" else self.args.workers * 2
        return build_dataloader(dataset, batch_size, workers, shuffle, rank)  # return dataloader

    def build_dataset(self, img_path, mode="train", batch=None, split="train"):
        """
        Build YOLO Dataset.

        Args:
            img_path (str): Path to the folder containing images.
            mode (str): `train` mode or `val` mode, users are able to customize different augmentations for each mode.
            batch (int, optional): Size of batches, this is for `rect`. Defaults to None.
        """
        gs = max(int(de_parallel(self.model).stride.max() if self.model else 0), 32)
        return build_tlc_dataset(self.args, img_path, batch, self.data, mode=mode, rect=mode == "val", stride=gs, table=self.data[split])

    def get_model(self, cfg=None, weights=None, verbose=True):
        """Return a YOLO detection model."""
        model = TLCDetectionModel(cfg, nc=self.data["nc"], verbose=verbose and RANK == -1)
        if weights:
            model.load(weights)
        return model

    def get_validator(self, loader=None):
        """Returns a DetectionValidator for YOLO model validation."""
        self.loss_names = "box_loss", "cls_loss", "dfl_loss"
        if not loader:
            loader = self.test_loader
        return TLCDetectionValidator(
            loader, save_dir=self.save_dir, args=copy.copy(self.args), _callbacks=self.callbacks, run=self._run,
        )

    def validate(self):
        # Validate on train set
        if not self._env_vars['COLLECTION_DISABLE'] and not self._env_vars['COLLECTION_VAL_ONLY'] and self.epoch in self._collection_epochs:
            self.train_validator(trainer=self, epoch=self.epoch)

        # Validate on val/test set
        return super().validate()
    
    def _do_train(self, world_size=1):
        super()._do_train(world_size=world_size)

        # Reduce embeddings
        self._run.reduce_embeddings_by_example_table_url(table_url=self.data["val"].url, method="pacmap", n_components=2)