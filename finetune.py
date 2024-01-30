import os
import comet_ml
from ultralytics import YOLO

# Set number of threads
os.environ['OMP_NUM_THREADS'] = '4'

# Initialize COMET logger, first log done in notebook where API key was asked, now seems to be saved in .comet.config
comet_ml.init()

# Initialize model and load matching weights
model = YOLO('yolov8s.yaml', task='detect').load('./../models/yolov8s.pt')

epochs = 300
batch = 128
optimizer = 'auto'

model.train(
    resume=False,
    data='custom_dataset.yaml',
    epochs=epochs,
    batch=batch,
    optimizer=optimizer,
    save=False,
    device=[0,1,2,3],
    project='fine-tune-cdv2',
    name=f'8sMask05-{epochs}e-{batch}b_{optimizer}',
    verbose=True,
    patience=25,
    cache=True
)