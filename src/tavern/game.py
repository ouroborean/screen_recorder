import asyncio
import contextvars
import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
import signal
from typing import Tuple

import cv2
import keyboard
import numpy as np
import pyautogui

resources_path = os.path.join(
    Path(__file__).parent.parent.parent, "resources\\")

target_fps = contextvars.ContextVar('target_fps', default=15)

class Camera:
    recording:bool
    upper_bounds: Tuple[int]
    size: Tuple[int]
    selecting_bounds: bool
    recording_running = False

    def __init__(self):
        self.recording = False
        self.selecting_bounds = False
        self.size = (0, 0)
        self.upper_bounds = (0,0)

    def define_upper_bounds(self, bounds: Tuple[int]):
        self.upper_bounds = bounds

    def define_lower_bounds(self, bounds: Tuple[int]):
        attempted_width = bounds[0] - self.upper_bounds[0]
        attempted_height = bounds[1] - self.upper_bounds[1]

        ten_diff = attempted_height % 10
        final_height = attempted_height + (10 - ten_diff)
        ten_diff = attempted_width % 10
        final_width = attempted_width + (10 - ten_diff)

        self.size = (final_width, final_height)

    def toggle(self):
        self.recording = not self.recording

class KeyLogger:



    def __init__(self, camera: Camera):
        self.log = ""
        self.camera = camera
    def release_callback(self, event):
        name = event.name
        if len(name) >= 1:
            if name == "=" and not self.camera.recording and not self.camera.selecting_bounds:
                self.camera.toggle()
            elif name == "r" and not self.camera.selecting_bounds and not self.camera.recording:
                self.camera.upper_bounds = (0,0)
                self.camera.size = (0,0)
                self.camera.selecting_bounds = True
                self.camera.define_upper_bounds(pyautogui.position())
            elif name == "r" and self.camera.selecting_bounds and not self.camera.recording:
                self.camera.selecting_bounds = False
                self.camera.define_lower_bounds(pyautogui.position())
            
        

    def start(self):
        keyboard.on_release(callback=self.release_callback)


class KillLogger:
    def __init__(self, vid_process, camera: Camera):
        self.log = ""
        self.vid_process = vid_process
        self.broken = False
        self.camera = camera

    def callback(self, event):
        name = event.name
        if len(name) >= 1:
            if name == "=" and not self.broken:
                self.vid_process.send_signal(signal.SIGTERM)
                self.broken = True
                self.camera.toggle()
                self.camera.recording_running = False
                self.camera.size = (0, 0)
                self.camera.upper_bounds = (0, 0)
            elif name == "alt+u":
                exit()
                
                
                

    def start(self):
        keyboard.on_release(callback=self.callback)


async def make_video(task_q: asyncio.Queue):
    consumer = asyncio.create_task(write_video(task_q))
    frame_count = 0
    print("Began frame capturing")
    while True:
        img = pyautogui.screenshot(region=(25, 135, 2560, 1440))
        frame = np.array(img)
        await task_q.put(frame)
        cv2.imshow("frame", frame)
        if cv2.waitKey(1) == ord('q'):
            break

        frame_count += 1
    await task_q.join()
    consumer.cancel()


async def write_video(queue: asyncio.Queue):
    fourcc = cv2.VideoWriter_fourcc(*"MP4V")
    out = cv2.VideoWriter(resources_path + "output.mp4", fourcc, 15,
                          (2560, 1440))
    print("initiated video writer")
    while True:
        item = await queue.get()
        logging.info("Got frame")
        rgb_frame = cv2.cvtColor(item, cv2.COLOR_BGR2RGB)
        out.write(rgb_frame)
        queue.task_done()


async def run():
    image_queue = asyncio.Queue(10)
    tasks = [
        asyncio.create_task(make_video(image_queue)),
    ]
    await asyncio.gather(*tasks)


async def run_ffmpeg(camera: Camera):
    print("Started recording!")
    region_string = ""
    if camera.size != (0, 0):
        region_string = f"-video_size {camera.size[0]}x{camera.size[1]} -offset_x {camera.upper_bounds[0]} -offset_y {camera.upper_bounds[1]} -show_region 1"
        print(region_string)
    ffmpeg_video_process = await asyncio.subprocess.create_subprocess_exec(
        "ffmpeg.exe",
        *shlex.split(
            f" -f dshow -i audio='Stereo Mix (Realtek(R) Audio)' -f gdigrab -threads 4 -framerate 30 {region_string} -i desktop -crf 35 -c:v h264_amf -b:v 9000k {resources_path}output-{int(time.time())}.mkv"
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    kill_logger = KillLogger(ffmpeg_video_process, camera)
    kill_logger.start()
    vstdout, vstderr = await ffmpeg_video_process.communicate()
    print(vstderr)

def main():
    camera = Camera()
    key_logger = KeyLogger(camera)
    key_logger.start()
    while True:
        if camera.recording and not camera.recording_running:
            camera.recording_running = True
            asyncio.run(run_ffmpeg(camera))

