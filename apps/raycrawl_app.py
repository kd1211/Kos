"""
Raycrawl -- an original first-person "corridor shooter" built with a
classic grid-based raycasting engine (the same core technique behind
early-90s FPS games): cast one ray per screen column with DDA, draw a
shaded vertical wall strip sized by (fisheye-corrected) distance, then
paint stationary enemy sprites on top using the per-column depth buffer
for occlusion, sorted back-to-front. Everything here -- the map, the
sprites, the sounds -- is original to Kos.

Touchscreen controls (single-touch, so only one held at a time, like
everything else on this device): a Forward/Back pad on the left, a
Turn Left/Right pad on the right, and a Fire button. Holding a control
keeps acting on it every tick via the same fixed-timestep pattern
Breakout uses in its draw() method -- there's no separate per-frame
update hook in this framework, so draw() both advances and renders.
"""

import math
import time
from ui import sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, ACCENT

# -- map: '1' wall, '0' floor. Must be rectangular with a solid border. --
MAP = [
    "11111111111111",
    "10000000000001",
    "10111011101001",
    "10100010001001",
    "10100010001001",
    "10101110111001",
    "10100000001001",
    "10111011101001",
    "10000000000001",
    "10011111100001",
    "10010000100001",
    "10010111100001",
    "10000001000001",
    "11111111111111",
]
MAP_H = len(MAP)
MAP_W = len(MAP[0])

VIEW_TOP = STATUS_BAR_H
VIEW_H = 210
HUD_Y = VIEW_TOP + VIEW_H + 14
CONTROLS_TOP = HUD_Y + 22

FOV = math.radians(66)
NUM_RAYS = 80
STRIP_W = SCREEN_W / NUM_RAYS
MAX_DEPTH = 18
PLAYER_RADIUS = 0.22

MOVE_SPEED = 2.3     # units/sec
ROT_SPEED = 2.3       # rad/sec
FIRE_COOLDOWN = 0.35
FIRE_CONE = math.radians(7)
FIRE_RANGE = 10.0

ENEMY_RANGE = 7.0
ENEMY_COOLDOWN = 1.6
ENEMY_DAMAGE = (5, 12)
ENEMY_COLOR = (210, 70, 70)

MINIMAP_SIZE = 76
MINIMAP_MARGIN = 8


def _is_wall(mx, my):
    if mx < 0 or mx >= MAP_W or my < 0 or my >= MAP_H:
        return True
    return MAP[my][mx] == "1"


def _cast_ray(px, py, angle):
    """Classic grid DDA: returns (distance, side). side=0 is a
    north/south-facing wall face, side=1 is east/west -- used to give
    the two orientations slightly different shading, a cheap trick that
    reads as real 3D."""
    sin_a, cos_a = math.sin(angle), math.cos(angle)
    map_x, map_y = int(px), int(py)

    delta_dist_x = abs(1 / cos_a) if cos_a != 0 else 1e30
    delta_dist_y = abs(1 / sin_a) if sin_a != 0 else 1e30

    if cos_a < 0:
        step_x = -1
        side_dist_x = (px - map_x) * delta_dist_x
    else:
        step_x = 1
        side_dist_x = (map_x + 1 - px) * delta_dist_x
    if sin_a < 0:
        step_y = -1
        side_dist_y = (py - map_y) * delta_dist_y
    else:
        step_y = 1
        side_dist_y = (map_y + 1 - py) * delta_dist_y

    side = 0
    for _ in range(64):
        if side_dist_x < side_dist_y:
            side_dist_x += delta_dist_x
            map_x += step_x
            side = 0
        else:
            side_dist_y += delta_dist_y
            map_y += step_y
            side = 1
        if _is_wall(map_x, map_y):
            break

    if side == 0:
        dist = (map_x - px + (1 - step_x) / 2) / cos_a
    else:
        dist = (map_y - py + (1 - step_y) / 2) / sin_a
    return max(dist, 0.0001), side


def _has_line_of_sight(x0, y0, x1, y1):
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 0.001:
        return True
    angle = math.atan2(y1 - y0, x1 - x0)
    wall_dist, _ = _cast_ray(x0, y0, angle)
    return wall_dist > dist


def _open_cells():
    return [(x, y) for y in range(MAP_H) for x in range(MAP_W) if MAP[y][x] == "0"]


class RaycrawlApp(App):
    name = "Raycrawl"
    icon = "\U0001F52B"

    def on_open(self):
        self.wants_animation = True
        open_cells = _open_cells()
        start = open_cells[len(open_cells) // 2]
        self.px, self.py = start[0] + 0.5, start[1] + 0.5
        self.angle = 0.0

        candidates = [c for c in open_cells
                      if math.hypot(c[0] - start[0], c[1] - start[1]) > 3]
        step = max(1, len(candidates) // 5)
        self.enemies = [
            {"x": c[0] + 0.5, "y": c[1] + 0.5, "alive": True, "cooldown": 0.0}
            for c in candidates[::step][:5]
        ]

        self.health = 100
        self.score = 0
        self.game_over = False
        self.won = False
        self.held = None
        self.fire_cooldown = 0.0
        self.flash = 0.0
        self.hit_flash = 0.0
        self.last_tick = time.time()

        pad = 78
        self._controls = {
            "forward": (14, CONTROLS_TOP, pad, pad),
            "back": (14, CONTROLS_TOP + pad + 10, pad, pad),
            "left": (SCREEN_W - 2 * pad - 24, CONTROLS_TOP, pad, pad),
            "right": (SCREEN_W - pad - 14, CONTROLS_TOP, pad, pad),
            "fire": (SCREEN_W - 2 * pad - 24, CONTROLS_TOP + pad + 10, 2 * pad + 10, pad),
        }
        self.buttons = [
            Button(SCREEN_W // 2 - 100, SCREEN_H - 34, 90, 28, "Restart", self.on_open, font=FONT_SM),
            Button(SCREEN_W // 2 + 10, SCREEN_H - 34, 90, 28, "Home", self.os.go_home, font=FONT_SM),
        ]

    # -- controls: press-and-hold like a virtual joystick --------------------
    def on_tap(self, x, y):
        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True
        for name, (rx, ry, rw, rh) in self._controls.items():
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.held = name
                return True
        return False

    def on_touch_move(self, x, y):
        pass  # holding persists regardless of where the finger drifts

    def on_touch_up(self):
        self.held = None

    # -- fixed-timestep game logic --------------------------------------------
    def _try_move(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        if not _is_wall(int(nx + math.copysign(PLAYER_RADIUS, dx)), int(self.py)):
            self.px = nx
        if not _is_wall(int(self.px), int(ny + math.copysign(PLAYER_RADIUS, dy))):
            self.py = ny

    def _fire(self):
        self.fire_cooldown = FIRE_COOLDOWN
        self.flash = 0.08
        sound.beep(1300, 45)
        best = None
        for e in self.enemies:
            if not e["alive"]:
                continue
            dx, dy = e["x"] - self.px, e["y"] - self.py
            dist = math.hypot(dx, dy)
            if dist > FIRE_RANGE:
                continue
            angle_to = math.atan2(dy, dx) - self.angle
            angle_to = (angle_to + math.pi) % (2 * math.pi) - math.pi
            if abs(angle_to) > FIRE_CONE:
                continue
            wall_dist, _ = _cast_ray(self.px, self.py, math.atan2(dy, dx))
            if wall_dist < dist - 0.2:
                continue  # a wall is in the way
            if best is None or dist < best[0]:
                best = (dist, e)
        if best:
            best[1]["alive"] = False
            self.score += 100
            sound.beep(300, 90)
            if all(not e["alive"] for e in self.enemies):
                self.won = True
                sound.chime()

    def _tick(self, dt):
        if self.game_over or self.won:
            return

        if self.held == "left":
            self.angle -= ROT_SPEED * dt
        elif self.held == "right":
            self.angle += ROT_SPEED * dt
        elif self.held == "forward":
            self._try_move(math.cos(self.angle) * MOVE_SPEED * dt,
                            math.sin(self.angle) * MOVE_SPEED * dt)
        elif self.held == "back":
            self._try_move(-math.cos(self.angle) * MOVE_SPEED * dt,
                            -math.sin(self.angle) * MOVE_SPEED * dt)
        elif self.held == "fire" and self.fire_cooldown <= 0:
            self._fire()

        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        self.flash = max(0.0, self.flash - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)

        for e in self.enemies:
            if not e["alive"]:
                continue
            e["cooldown"] = max(0.0, e["cooldown"] - dt)
            dist = math.hypot(e["x"] - self.px, e["y"] - self.py)
            if dist <= ENEMY_RANGE and e["cooldown"] <= 0 and \
                    _has_line_of_sight(e["x"], e["y"], self.px, self.py):
                e["cooldown"] = ENEMY_COOLDOWN
                import random
                dmg = random.randint(*ENEMY_DAMAGE)
                self.health -= dmg
                self.hit_flash = 0.15
                sound.beep(180, 120)
                if self.health <= 0:
                    self.health = 0
                    self.game_over = True

    # -- rendering --------------------------------------------------------------
    def draw(self, draw, canvas):
        now = time.time()
        dt_budget = now - self.last_tick
        dt_budget = min(dt_budget, 0.2)  # avoid a huge catch-up burst after a stall
        while dt_budget >= 0.02:
            self._tick(0.02)
            dt_budget -= 0.02
            self.last_tick += 0.02
        if dt_budget > 0:
            self.last_tick = now

        draw.rectangle([0, VIEW_TOP, SCREEN_W, VIEW_TOP + VIEW_H // 2], fill=(28, 28, 36))
        draw.rectangle([0, VIEW_TOP + VIEW_H // 2, SCREEN_W, VIEW_TOP + VIEW_H], fill=(18, 18, 22))

        depth_buffer = [MAX_DEPTH] * NUM_RAYS
        for col in range(NUM_RAYS):
            ray_angle = self.angle - FOV / 2 + (col / NUM_RAYS) * FOV
            dist, side = _cast_ray(self.px, self.py, ray_angle)
            corrected = dist * math.cos(ray_angle - self.angle)
            depth_buffer[col] = corrected

            wall_h = min(VIEW_H, VIEW_H / max(corrected, 0.0001))
            y0 = VIEW_TOP + VIEW_H // 2 - wall_h / 2
            y1 = VIEW_TOP + VIEW_H // 2 + wall_h / 2

            shade = max(0.25, 1.0 - corrected / MAX_DEPTH)
            base = 150 if side == 0 else 110
            c = int(base * shade)
            color = (c, c, min(255, c + 20))

            x0 = col * STRIP_W
            draw.rectangle([x0, y0, x0 + STRIP_W + 1, y1], fill=color)

        # sprites: back-to-front so nearer enemies draw on top
        alive = [e for e in self.enemies if e["alive"]]
        alive.sort(key=lambda e: -math.hypot(e["x"] - self.px, e["y"] - self.py))
        for e in alive:
            dx, dy = e["x"] - self.px, e["y"] - self.py
            dist = math.hypot(dx, dy)
            angle_to = math.atan2(dy, dx) - self.angle
            angle_to = (angle_to + math.pi) % (2 * math.pi) - math.pi
            if abs(angle_to) > FOV / 2 + 0.2 or dist < 0.2:
                continue
            screen_x = (0.5 + angle_to / FOV) * SCREEN_W
            col = int(screen_x / STRIP_W)
            if 0 <= col < NUM_RAYS and dist > depth_buffer[col] + 0.15:
                continue  # behind a wall
            size = max(6, min(120, VIEW_H / max(dist, 0.2) * 0.5))
            cy = VIEW_TOP + VIEW_H // 2
            shade = max(0.3, 1.0 - dist / MAX_DEPTH)
            color = tuple(int(c * shade) for c in ENEMY_COLOR)
            draw.ellipse([screen_x - size / 2, cy - size / 2, screen_x + size / 2, cy + size / 2],
                         fill=color, outline=(0, 0, 0))
            eye_y = cy - size * 0.15
            draw.ellipse([screen_x - size * 0.15, eye_y - size * 0.08,
                          screen_x + size * 0.15, eye_y + size * 0.08], fill=(255, 240, 200))

        if self.flash > 0:
            draw.rectangle([0, VIEW_TOP, SCREEN_W, VIEW_TOP + VIEW_H], fill=(255, 255, 255))
        elif self.hit_flash > 0:
            overlay_alpha = self.hit_flash / 0.15
            draw.rectangle([0, VIEW_TOP, SCREEN_W, VIEW_TOP + VIEW_H],
                            outline=(220, 30, 30), width=int(6 * overlay_alpha) + 1)

        self._draw_crosshair(draw)
        self._draw_minimap(draw)

        alive_count = sum(1 for e in self.enemies if e["alive"])
        draw.text((SCREEN_W // 2, HUD_Y),
                   f"HP {self.health}   Score {self.score}   Enemies {alive_count}",
                   font=FONT_SM, fill=(255, 255, 255), anchor="mm")

        self._draw_controls(draw)

        if self.game_over:
            self._draw_banner(draw, "You Died", (230, 90, 90))
        elif self.won:
            self._draw_banner(draw, "Sector Cleared!", (120, 220, 140))

        for b in self.buttons:
            b.draw(draw)

    def _draw_crosshair(self, draw):
        cx, cy = SCREEN_W // 2, VIEW_TOP + VIEW_H // 2
        draw.line([cx - 8, cy, cx - 3, cy], fill=(255, 255, 255), width=2)
        draw.line([cx + 3, cy, cx + 8, cy], fill=(255, 255, 255), width=2)
        draw.line([cx, cy - 8, cx, cy - 3], fill=(255, 255, 255), width=2)
        draw.line([cx, cy + 3, cx, cy + 8], fill=(255, 255, 255), width=2)

    def _draw_minimap(self, draw):
        x0 = SCREEN_W - MINIMAP_SIZE - MINIMAP_MARGIN
        y0 = VIEW_TOP + MINIMAP_MARGIN
        cell = MINIMAP_SIZE / max(MAP_W, MAP_H)
        draw.rectangle([x0, y0, x0 + MINIMAP_SIZE, y0 + MINIMAP_SIZE], fill=(0, 0, 0))
        for my in range(MAP_H):
            for mx in range(MAP_W):
                if MAP[my][mx] == "1":
                    px0, py0 = x0 + mx * cell, y0 + my * cell
                    draw.rectangle([px0, py0, px0 + cell, py0 + cell], fill=(90, 90, 100))
        for e in self.enemies:
            if e["alive"]:
                ex, ey = x0 + e["x"] * cell, y0 + e["y"] * cell
                draw.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=ENEMY_COLOR)
        px, py = x0 + self.px * cell, y0 + self.py * cell
        hx, hy = px + math.cos(self.angle) * 6, py + math.sin(self.angle) * 6
        draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(120, 220, 255))
        draw.line([px, py, hx, hy], fill=(120, 220, 255), width=1)

    def _draw_controls(self, draw):
        labels = {"forward": "\u25B2", "back": "\u25BC", "left": "\u25C0",
                  "right": "\u25B6", "fire": "FIRE"}
        for name, (x, y, w, h) in self._controls.items():
            active = (self.held == name)
            bg = ACCENT if active else (46, 46, 56)
            draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=bg)
            font = FONT_MD if name == "fire" else FONT_LG
            draw.text((x + w // 2, y + h // 2), labels[name], font=font,
                       fill=(255, 255, 255), anchor="mm")

    def _draw_banner(self, draw, text, color):
        draw.rectangle([0, VIEW_TOP + VIEW_H // 2 - 30, SCREEN_W, VIEW_TOP + VIEW_H // 2 + 30],
                        fill=(0, 0, 0))
        draw.text((SCREEN_W // 2, VIEW_TOP + VIEW_H // 2), text, font=FONT_LG,
                   fill=color, anchor="mm")
