"""Predictable overview, plan and eye-level cameras in stage coordinates."""
from __future__ import annotations

import math
import threading

import numpy as np


class CameraController:
    def __init__(self, target, radius, up_axis, rooms=(), plan_radius=None):
        self.home = np.asarray(target, dtype=np.float64)
        self.base_radius = float(radius)
        self.plan_radius = float(plan_radius or radius)
        self.up_index = 2 if up_axis == "Z" else 1
        self.up = np.eye(3)[self.up_index]
        self.rooms = {room['id']: room for room in rooms}
        self.lock = threading.RLock()
        self.pointer = None
        self.dragging = False
        self.set_view('overview')

    def set_view(self, view, room_id=None):
        if view not in {'overview', 'plan', 'room', 'interior'}:
            raise ValueError('Unknown camera view')
        if view in {'room', 'interior'} and room_id not in self.rooms:
            raise ValueError('Choose a room first')
        with self.lock:
            self.view = view
            self.room_id = room_id
            self.target = self.home.copy()
            self.yaw = -math.pi / 2
            self.pitch = math.radians(62)
            self.radius = self.base_radius
            if view == 'plan':
                self.pitch = math.pi / 2 - 0.0001
                self.radius = self.plan_radius
            elif view in {'room', 'interior'}:
                room = self.rooms[room_id]
                low, high = np.asarray(room['min']), np.asarray(room['max'])
                self.target = (low + high) / 2
                self.target[self.up_index] = self.home[self.up_index] * 0.35
                self.radius = max(4, np.linalg.norm(high - low) * 1.6)
                if view == 'interior':
                    self.eye = np.asarray(room['eye'], dtype=np.float64)
                    direction = np.asarray(room['look_at']) - self.eye
                    h = [i for i in range(3) if i != self.up_index]
                    self.yaw = math.atan2(direction[h[1]], direction[h[0]])
                    self.pitch = math.atan2(direction[self.up_index], np.linalg.norm(direction[h]))
            self.dragging = False
            self.pointer = None

    def state(self):
        with self.lock:
            return {'view': self.view, 'room': self.room_id, 'radius': self.radius,
                    'yaw': self.yaw, 'pitch': self.pitch}

    def zoom(self, steps):
        with self.lock:
            if self.view == 'interior':
                direction = self._direction()
                direction[self.up_index] = 0
                self.eye += direction * max(-2, min(2, steps)) * 0.25
            else:
                self.radius = float(np.clip(self.radius * math.exp(-steps * 0.10),
                                           1.5, self.base_radius * 3))

    def on_input(self, event, ovstream):
        # Camera presets live in labelled buttons. A random key must not
        # unexpectedly reset the view while navigating or tabbing controls.
        if event.type != ovstream.InputEventType.MOUSE:
            return
        with self.lock:
            mouse = event.mouse
            if mouse.type == ovstream.MouseEventType.BUTTON:
                if mouse.data == ovstream.MouseButton.LEFT:
                    self.dragging = mouse.button_state == ovstream.KeyState.DOWN
                    self.pointer = (mouse.x, mouse.y) if self.dragging else None
            elif mouse.type == ovstream.MouseEventType.MOVE and self.dragging:
                if self.pointer is not None:
                    dx, dy = mouse.x - self.pointer[0], mouse.y - self.pointer[1]
                    self.yaw -= dx * 0.005
                    if self.view != 'plan':
                        sign = -1 if self.view == 'interior' else 1
                        low = -1.2 if self.view == 'interior' else 0.1
                        self.pitch = float(np.clip(self.pitch + sign * dy * 0.005, low, 1.5))
                self.pointer = (mouse.x, mouse.y)
            elif mouse.type == ovstream.MouseEventType.WHEEL:
                self.zoom(mouse.scroll_y)

    def _direction(self):
        h = math.cos(self.pitch)
        if self.up_index == 2:
            return np.array([h * math.cos(self.yaw), h * math.sin(self.yaw), math.sin(self.pitch)])
        return np.array([h * math.cos(self.yaw), math.sin(self.pitch), h * math.sin(self.yaw)])

    def matrix(self, elapsed=0):
        with self.lock:
            direction = self._direction()
            if self.view == 'interior':
                eye, forward = self.eye.copy(), direction
            else:
                eye = self.target + direction * self.radius
                forward = -direction
            right = np.cross(forward, self.up)
            right /= np.linalg.norm(right)
            up = np.cross(right, forward)
            matrix = np.eye(4, dtype=np.float64)
            matrix[0, :3], matrix[1, :3], matrix[2, :3] = right, up, -forward
            matrix[3, :3] = eye
            return matrix
