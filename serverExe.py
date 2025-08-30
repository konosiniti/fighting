import socket
import pygame
import pickle
import threading
import json
import copy
import time
import random
import math
import sys
import os

# --- 初期化 ---
pygame.init()
WIDTH, HEIGHT = 992, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
SPEED = 4
JUMP_VELOCITY = -8
GRAVITY = 0.5
SHIELD_GAGE = 500
SHIELD_COST = 5
offset_x = 0
offset_y = 0
font = pygame.font.SysFont(None, 20)
HOST = '0.0.0.0'
PORT = 5050

# --- エフェクトの登録と管理用 ---
effect_defs = {}
active_effects = []

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstallerが実行ファイルを展開する一時フォルダ
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# --- Mapクラス ---
class Map:
    def __init__(self, map_data):
        self.tile_width = map_data["tilewidth"]
        self.tile_height = map_data["tileheight"]
        self.width = map_data["width"]
        self.height = map_data["height"]
        self.layers = map_data["layers"]

        self.tilesets = []
        for tileset in map_data["tilesets"]:
            image = pygame.image.load(tileset["image"]).convert_alpha()
            columns = image.get_width() // self.tile_width
            self.tilesets.append({
                "firstgid": tileset["firstgid"],
                "image": image,
                "columns": columns
            })

        self.collide_layer = None
        for layer in self.layers:
            if layer.get("name") == "collideObj" and layer.get("type") == "tilelayer":
                self.collide_layer = layer
                break

    def get_tile(self, index):
        if index == 0:
            return None
        for tileset in reversed(self.tilesets):
            if index >= tileset["firstgid"]:
                local_index = index - tileset["firstgid"]
                max_index = (tileset["image"].get_width() // self.tile_width) * (tileset["image"].get_height() // self.tile_height)
                if local_index < 0 or local_index >= max_index:
                    return None
                x = (local_index % tileset["columns"]) * self.tile_width
                y = (local_index // tileset["columns"]) * self.tile_height
                return tileset["image"].subsurface(pygame.Rect(x, y, self.tile_width, self.tile_height))
        return None

    def draw(self, surface, offset_x, offset_y):
        start_col = int(offset_x // self.tile_width)
        start_row = int(offset_y // self.tile_height)
        end_col = int((offset_x + WIDTH) // self.tile_width) + 1
        end_row = int((offset_y + HEIGHT) // self.tile_height) + 1

        for layer in self.layers:
            if layer["type"] == "tilelayer":
                for row in range(start_row, min(end_row, self.height)):
                    for col in range(start_col, min(end_col, self.width)):
                        tile_index = layer["data"][row * self.width + col]
                        tile = self.get_tile(tile_index)
                        if tile:
                            surface.blit(tile, (
                                col * self.tile_width - offset_x,
                                row * self.tile_height - offset_y
                            ))

# --- playerのアニメーションを管理 ---
class Animation:
    def __init__(self, image_path, frame_width, frame_height, num_frames, speed):  # ← speed追加
        sheet = pygame.image.load(image_path).convert_alpha()
        self.frames = []
        for i in range(num_frames):
            rect = pygame.Rect(i * frame_width, 0, frame_width, frame_height)
            frame = sheet.subsurface(rect).copy()
            self.frames.append(frame)
        self.num_frames = num_frames
        self.index = 0
        self.speed = speed  # 1フレームあたり何秒？
        self.last_update = time.time()

    def get_frame(self):
        current_time = time.time()
        if current_time - self.last_update >= self.speed:
            self.index = (self.index + 1) % self.num_frames
            self.last_update = current_time
        return self.frames[self.index]

# --- 職業のデータ ---
job_data = {
    "Warrior": {
        "hp": 4500,  # ↑ タンク寄りなのでHP増
        "defense": 40,  # ↑ 防御も高めに
        "damaged": 45,  # ↓ 通常攻撃力は控えめ
        "skills": {
            "wave_strike": {"active": False, "damaged": 300, "cooldown": 0, "end_time": 0, "description": "特に説明なく普通に攻撃"},  # ↓控えめ
            "chargeBoost": {"active": False, "damaged": 250, "speed": 10, "cooldown": 0, "end_time": 0, "description": "突進攻撃:相手に向かって突進"},  # ↑CD追加
            "all_death_damage": {"active": False, "damaged": 1500, "cooldown": 0, "end_time": 0, "description": "自爆攻撃:自分の体力を削り爆発"}  # ↑威力UP・CD追加
        }
    },
    "Wizard": {
        "hp": 3000,  # ↓脆めに
        "defense": 10,
        "damaged": 25,
        "skills": {
            "heal": {"active": False, "healed": False, "cooldown": 0, "end_time": 0, "amount": 50, "next_time": 5, "description": "回復"},  # ↑CD追加
            "strength_buff": {"active": False, "multipliers": {"damaged": 1.8}, "buffed": False, "cooldown": 0, "end_time": 0, "description": "攻撃力上昇"},  # ↓倍率
            "resistance_buff": {"active": False, "multipliers": {"defense": 2.5}, "buffed": False, "cooldown": 0, "end_time": 0, "description": "防御力上昇"},  # ↓倍率
            "Element_aura": {"active": False, "damaged": 1200, "cooldown": 0, "end_time": 0, "description": "魔法最大奥義"}  # ↓調整
        }
    },
    "Assassin": {
        "hp": 2600,
        "defense": 15,  # ↓打たれ弱く
        "damaged": 55,  # ↑通常攻撃強め
        "skills": {
            "criticalAttackMulti": {"active": False, "damaged": 400, "cooldown":0, "end_time": 0, "hits": 3, "interval": 0.35, "description": "乱刀:複数回連続で攻撃"},  # ↓威力少し調整
            "shadow_move": {"active": False, "damaged": 100, "cooldown": 0, "end_time": 0, "description": "影に潜り、相手のところまで移動、少しの間相手をスタン"},  # ↑威力UP
            "dummy": {"active": False, "damaged": 1000, "speed": 20, "cooldown": 0, "end_time": 0, "description": "相手を攻撃、とおすぎると自分にダメージが食らう"}  # ↓やや弱体
        }
    },
    "Player": {
        "hp": 33000,
        "defense": 70,
        "damaged": 120,
        "skills": {
            "heal": {"active": False, "healed": False, "cooldown": 5, "end_time": 0, "amount": 20000, "description": "チート級のヒール:ランダムで回復"},
            "create_isGod": {"active": False, "damaged": -2000, "cooldown": 0, "end_time": 0, "description": "相手を回復させる、絶対に敵を死なせない"} 
        }
    },
    "Sniper": {
        "hp": 3100,
        "defense": 20,
        "damaged": 70,
        "skills": {
            "far_snipe": {"active": False, "damaged": 650, "cooldown": 0, "end_time": 0, "description": "遠距離から高威力攻撃"},  # ↓威力
            "claymore_trap": {"active": False, "damaged": 400, "duration": 8, "cooldown": 0, "end_time": 0, "description": "罠設置、移動速度低下"},  # ↑CD
            "over_heat": {"active": False, "damaged": 1, "multipliers": {"attack_cooldown": 0.7, "damaged": 1.3}, "buffed": False, "cooldown": 0, "end_time": 0, "description": "連射可能化"}  # ↑倍率調整
        }
    },
    "Berserker": {
        "hp": 1800,  # ↑少し増やす
        "defense": 25,  # ↓やや柔らかく
        "damaged": 50,
        "skills": {
            "berserked": {"active": False, "damaged": 1, "multipliers": {"defense": 1.5}, "debuffed": False, "cooldown": 0, "end_time": 0, "description": "防御力上昇"},
            "boost": {"active": False, "damaged": 1, "multipliers": {"attack_cooldown": 0.5, "damaged": 2}, "buffed": False, "cooldown": 0, "end_time": 0, "description": "攻撃速度上昇＋攻撃力増加"}  # ↓倍率弱体
        }
    },
    "Gambler": {
        "hp": 2800,  # ↓バランス調整
        "defense": 25,
        "damaged": 50,
        "skills": {
            # スキル未実装、今後ランダム系やリスクリターン系を追加可能
        }
    }
}


def load_map(path):
    with open(path, "r") as f:
        return json.load(f)


# --- 汎用エフェクトアニメーションクラス ---
class EffectAnimation:
    def __init__(self, name, image_path, frame_width, frame_height, num_frames, speed=0.1):
        self.name = name
        sheet = pygame.image.load(image_path).convert_alpha()
        self.frames = []
        for i in range(num_frames):
            rect = pygame.Rect(i * frame_width, 0, frame_width, frame_height)
            self.frames.append(sheet.subsurface(rect).copy())
        self.speed = speed

    def create_instance(self, x, y):
        return {
            "frames": self.frames,
            "index": 0,
            "x": x,
            "y": y,
            "last_update": time.time(),
            "speed": self.speed
        }


def register_effect(name, image_path, frame_width, frame_height, num_frames, speed=0.1):
    effect_defs[name] = EffectAnimation(name, image_path, frame_width, frame_height, num_frames, speed)

# --- エフェクトのアニメーションの描画 ---
def update_and_draw_effects(surface, offset_x=0, offset_y=0):
    for effect in active_effects[:]:
        now = time.time()
        if now - effect["last_update"] >= effect["speed"]:
            effect["index"] += 1
            effect["last_update"] = now

        if 0 <= effect["index"] < len(effect["frames"]):
            frame = effect["frames"][effect["index"]]
            rect = frame.get_rect(center=(effect["x"] - offset_x, effect["y"] - offset_y))
            surface.blit(frame, rect)
        else:
            active_effects.remove(effect)
    for effect in active_effects[:]:
        now = time.time()
        if now - effect["last_update"] >= effect["speed"]:
            effect["index"] += 1
            effect["last_update"] = now
        if effect["index"] < len(effect["frames"]):
            frame = effect["frames"][effect["index"]]
            rect = frame.get_rect(center=(effect["x"] - offset_x, effect["y"] - offset_y))
            surface.blit(frame, rect)
        else:
            active_effects.remove(effect)


def send_skill_effect(name, x, y, duration=0.5):
    skill_effects.append({
        "type": name,
        "x": x,
        "y": y,
        "start": time.time(),
        "duration": duration
    })

# --- 魔法使いのエフェクト ---
element_effects = [
    "fire", "water", "lightning",
    "earth", "wind", "ice"
]

skill_effects = []  # エフェクト保存用リスト
traps = []

#起動時に一度だけ登録
register_effect("stun", resource_path("img/effects/stun.png"), 192, 192, 10, 0.05)
register_effect("wave_strike", resource_path("img/effects/wave_strike.png"), 64, 64, 1, 0.08)
register_effect("all_death_damage", resource_path("img/effects/all_death_damage.png"), 120, 120, 7, 0.08)
register_effect("normal_slash", resource_path("img/effects/normal_slash.png"), 120, 120, 5, 0.08)
register_effect("criticalAttackMulti", resource_path("img/effects/criticalAttackMulti.png"), 640, 480, 24, 0.08)
register_effect("shadow_move", resource_path("img/effects/shadow_move.png"), 320, 120, 8, 0.1)
register_effect("charge_boost", resource_path("img/effects/charge_boost.png"), 120, 120, 5, 0.1)
register_effect("wave_strike", resource_path("img/effects/wave_strike.png"), 120, 120, 7, 0.08)
register_effect("claymore_trap", resource_path("img/effects/claymore_trap.png"), 320, 120, 6, 0.1)
register_effect("Element_aura", resource_path("img/effects/Element_aura.png"), 120, 120, 8, 0.1)
for name in element_effects:
    register_effect(name, resource_path(f"img/effects/{name}.png"), 120, 120, 8, 0.1)



def get_sprite(sheet, col, row, width, height):
    sprite = pygame.Surface((width, height), pygame.SRCALPHA)
    sprite.blit(sheet, (0, 0), pygame.Rect(col * width, row * height, width, height))
    return sprite


# --- playerのアニメーションの定義
def create_animations():
    return {
        'run': Animation(resource_path("アニメーション/Run.png"), 128, 128, 8, 0.1),
        'idle': Animation(resource_path("アニメーション/Idle.png"), 128, 128, 4, 0.45),
        'jump': Animation(resource_path("アニメーション/Jump.png"), 128, 128, 10, 0.85),
        'walk': Animation(resource_path("アニメーション/Walk.png"), 128, 128, 8, 0.25),
        'dead': Animation(resource_path("アニメーション/Dead.png"), 128, 128, 3, 0.25),
        'shield': Animation(resource_path("アニメーション/Shield.png"), 128, 128, 2, 0.25),
        'attack1': Animation(resource_path("アニメーション/Attack_1.png"), 128, 128, 4, 0.01),
        'attack2': Animation(resource_path("アニメーション/Attack_2.png"), 128, 128, 3, 1),
        'attack3': Animation(resource_path("アニメーション/Attack_3.png"), 128, 128, 4, 1),
        'hurt': Animation(resource_path("アニメーション/Hurt.png"), 128, 128, 3, 0.25)
    }


shieldsheet = pygame.image.load(resource_path("img/effects/shield.png")).convert_alpha()

all_map = [
    resource_path("map/field.json"),
    resource_path("map/town.json"),
    resource_path("map/guild.json"),
    resource_path("map/guild2.json"),
    resource_path("map/forest.json"),
    resource_path("map/wetland.json"),
    resource_path("map/cave.json"),
    resource_path("map/lava.json"),
    resource_path("map/battle.json")
]


# shieldスプライトは5フレーム分 (i=5〜1)
player_shields = [get_sprite(shieldsheet, i, 0, 50, 50) for i in range(5, 0, -1)]
player_size = (40, 115)
players = {}
players_lock = threading.Lock()
def players_snapshot():
    # Shallow copy is enough; values (player dicts) are shared so mutations to pdata reflect back.
    with players_lock:
        return dict(players)


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)

print(f"Waiting for connections on {HOST}:{PORT}...")
#selected_map = random.choice(all_map)  #ランダム用
selected_map = all_map[0]   #初期マップ
map_data = load_map(selected_map)
game_map = Map(map_data)


# --- シールドゲージの描画
def draw_shield_gage(surface, x, y, gage, max_gage=500, width=40, height=5):
    ratio = gage / max_gage
    pygame.draw.rect(surface, (100, 100, 100), (x, y - 15, width, height))
    pygame.draw.rect(surface, (0, 200, 255), (x, y - 15, width * ratio, height))


# --- playerの体力の描画
def draw_health_bar(surface, x, y, hp, max_hp=100, width=40, height=5):
    ratio = hp / max_hp
    pygame.draw.rect(surface, (255, 0, 0), (x, y - 10, width, height))
    pygame.draw.rect(surface, (0, 255, 0), (x, y - 10, width * ratio, height))


# --- player_idの描画
def draw_name(surface, x, y, player_id, width=40, height=40):
    text_surface = font.render(f"{player_id}", True, (0, 0, 0), (255, 255, 255))
    text_rect = text_surface.get_rect()
    text_rect.center = (x + width // 2, y - 20)
    surface.blit(text_surface, text_rect)


# --- player同士の当たり判定処理 ---
def handle_collision(player_id):
    with players_lock:
        player_rect = players[player_id]["rect"]
    
    for other_id, other_data in players_snapshot().items():
        if other_id != player_id:
            other_rect = other_data["rect"]
            if player_rect.colliderect(other_rect):
                # 上から着地
                if (player_rect.bottom > other_rect.top and
                    player_rect.top < other_rect.top and
                    player_rect.centery < other_rect.centery):
                    player_rect.bottom = other_rect.top
                    players[player_id]["vel_y"] = 0
                    # on_groundは他プレイヤーでは設定しない

                # 下からぶつかった（ジャンプ中）
                elif (player_rect.top < other_rect.bottom and
                      player_rect.bottom > other_rect.bottom and
                      player_rect.centery > other_rect.centery):
                    player_rect.top = other_rect.bottom
                    players[player_id]["vel_y"] = 0

                # 左からぶつかった（→方向）
                elif (player_rect.right > other_rect.left and
                      player_rect.left < other_rect.left and
                      player_rect.centerx < other_rect.centerx):
                    player_rect.right = other_rect.left

                # 右からぶつかった（←方向）
                elif (player_rect.left < other_rect.right and
                      player_rect.right > other_rect.right and
                      player_rect.centerx > other_rect.centerx):
                    player_rect.left = other_rect.right


# --- マップとの当たり判定処理 ---
def handle_map_collision(player):
    if not game_map.collide_layer:
        return

    tile_w, tile_h = game_map.tile_width, game_map.tile_height
    layer = game_map.collide_layer
    rect = player["rect"]
    left = rect.left // tile_w
    right = rect.right // tile_w
    top = rect.top // tile_h
    bottom = rect.bottom // tile_h

    # 垂直方向の衝突
    for row in range(top, bottom + 1):
        for col in range(left, right + 1):
            if row < 0 or row >= game_map.height or col < 0 or col >= game_map.width:
                continue
            tile_index = layer["data"][row * game_map.width + col]
            if tile_index == 324:
                tile_rect = pygame.Rect(col * tile_w, row * tile_h, tile_w, tile_h)
                if rect.colliderect(tile_rect):
                    if player["vel_y"] > 0 and rect.bottom > tile_rect.top and rect.top < tile_rect.top:
                        rect.bottom = tile_rect.top
                        player["vel_y"] = 0
                        player["on_ground"] = True
                    elif player["vel_y"] < 0 and rect.top < tile_rect.bottom and rect.bottom > tile_rect.bottom:
                        rect.top = tile_rect.bottom
                        player["vel_y"] = 0

    # 水平方向の衝突（on_ground のときのみ）
    if player["on_ground"]:
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if row < 0 or row >= game_map.height or col < 0 or col >= game_map.width:
                    continue
                tile_index = layer["data"][row * game_map.width + col]
                if tile_index == 324:
                    tile_rect = pygame.Rect(col * tile_w, row * tile_h, tile_w, tile_h)
                    if rect.colliderect(tile_rect):
                        if rect.right > tile_rect.left and rect.left < tile_rect.left:
                            rect.right = tile_rect.left
                        elif rect.left < tile_rect.right and rect.right > tile_rect.right:
                            rect.left = tile_rect.right


# --- 主な処理 ---
def handle_client(client_socket, client_address, player_id):
    
    print(f"Player {player_id} connected from {client_address}")
    client_socket.send(pickle.dumps(player_id))
    client_socket.send(pickle.dumps(selected_map))
    job = pickle.loads(client_socket.recv(1024))
    stats = job_data.get(job, job_data["Player"])

    player_x, player_y = 100 + player_id * 100, HEIGHT - player_size[1] - 150

    print(f"Player {player_id} selected job: {job}")

    with players_lock:
        players[player_id] = {
        "rect": pygame.Rect(player_x, player_y, *player_size),
        "vel_y": 0,
        "on_ground": True,
        "job": job,
        "damaged": stats["damaged"],
        "hp": stats["hp"],
        "defense": stats["defense"],
        "maxHp": stats["hp"],
        "alive": True,
        "animations": create_animations(),
        "animation_state": "idle",
        "animation_index": 0,
        "last_anim_time": time.time(),
        "facing_right": True,
        "isShield": False,
        "ShieldGage": SHIELD_GAGE,
        "ShieldRecovering": False,
        "attack_cooldown": 0,
        "buffed_effects": [],
        "attack_status": "normal",
        "element_type": "fire",  # 初期属性
        "common": {
            "jump_skill": {"active": False, "cooldown": 0, "end_time": 0},
            "stun": {"active": False, "stuned": False, "cooldown": 0, "end_time": 0},
        },
        "job_skill": copy.deepcopy(stats.get("skills", {})),
        "mouse_pos": (0,0),
    }
    previous_keys = [False] * 15  # 前回のキー状態（長押し検出防止用）
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            recv_data = pickle.loads(data)
            keys = recv_data.get("keys", [False] * 15)
            mouse_pos = recv_data.get("mouse_pos", (0, 0))  # ← マウス座標の取り出し

            with players_lock:
                player = players[player_id]
                player["mouse_pos"] = mouse_pos  # ← 必要であればプレイヤー情報に保持
            
            just_pressed_13 = keys[13] and not previous_keys[13] #z
            just_pressed_14 = keys[14] and not previous_keys[14] #m
            if keys[12] and player["alive"] == False:
                print(f"サーバで死亡を確認  keys[12]{keys[12]}")
                print(f"Player {player_id} respawned.")
                keys[12] = False
                player["hp"] = player["maxHp"]
                player["rect"].x, player["rect"].y = 100 + player_id * 100, HEIGHT - player_size[1] - 150
                player["alive"] = True
                player["vel_y"] = 0
                player["ShieldGage"] = SHIELD_GAGE
                for skill in player["common"].values():
                    skill["active"] = False
                    skill["cooldown"] = 10
                    skill["stuned"] = False if "stuned" in skill else skill.get("stuned", False)
                for skill in player["job_skill"].values():
                    skill["active"] = False
                    skill["cooldown"] = 10
                print(f"復活処理終了 keys[12] = {keys[12]}")
                #pass

            if player["alive"]: #生きてたら作動するゾーン
                current_time = time.time()
                # スキル効果終了判定
                for skill_name, skill in player["common"].items():
                    if skill["active"] and current_time >= skill["end_time"]:
                        skill["active"] = False
                        print(f"Player {player_id} {skill_name} ended.")
                # クールダウン減少
                for skill in player["common"].values():
                    if skill["cooldown"] > 0:
                        skill["cooldown"] -= 1
                
                # --- 移動処理 ---
                moved = False
                if not player["common"]["stun"]["stuned"] and not player["isShield"]:
                    if keys[0] and player["rect"].x > 0:
                        player["rect"].x -= SPEED
                        player["facing_right"] = False
                        moved = True

                    if keys[1] and player["rect"].x + player["rect"].width < WIDTH:
                        player["rect"].x += SPEED
                        player["facing_right"] = True
                        moved = True

                    if keys[2] and player["on_ground"]:
                        player["vel_y"] = JUMP_VELOCITY
                        player["on_ground"] = False
                        if player["animation_state"] != "jump":
                            player["animation_state"] = "jump"
                            player["animations"]["jump"].index = 0
                    elif moved:
                        if player["animation_state"] != "run":
                            player["animation_state"] = "run"
                            player["animations"]["run"].index = 0
                    else:
                        if player["animation_state"] != "idle":
                            player["animation_state"] = "idle"
                            player["animations"]["idle"].index = 0

                # --- パンチ ---処理
               # --- パンチ処理 ---
                if keys[4]:
                    if player["attack_cooldown"] <= 0:
                        for target_id, target in players_snapshot().items():
                            if target_id != player_id and target["hp"] > 0 and target["alive"] and not player["isShield"]:
                                dx = player["rect"].centerx - target["rect"].centerx
                                dy = player["rect"].centery - target["rect"].centery
                                dist = (dx**2 + dy**2) ** 0.5

                                # 連射モード倍率
                                cool_multiplier = 1.0

                                # Sniperのover_heat
                                if player["job"] == "Sniper":
                                    buff = player["job_skill"].get("over_heat", {})
                                    if buff.get("buffed", False) and current_time < buff.get("end_time", 0):
                                        cool_multiplier = buff.get("multipliers", {}).get("attack_cooldown", 1.0)

                                # Berserkerのboost
                                if player["job"] == "Berserker":
                                    boost = player["job_skill"].get("boost", {})
                                    if boost.get("buffed", False) and current_time < boost.get("end_time", 0):
                                        cool_multiplier = boost.get("multipliers", {}).get("attack_cooldown", 1.0)

                                # 攻撃アニメ
                                if player["animation_state"] != "attack1":
                                    player["animation_state"] = "attack1"
                                    player["animations"]["attack1"].index = 0

                                if player["animation_state"].startswith("attack"):
                                    animation = player["animations"]["attack1"]
                                    if animation.index >= animation.num_frames - 1:
                                        player["animation_state"] = "idle"
                                        animation.index = 0

                                # 距離判定
                                if player["job"] == "Sniper":
                                    # マウス座標を取得
                                    mx, my = player.get("mouse_pos", (0, 0))  # プレイヤーの送信データにマウス座標が含まれている前提

                                    # ターゲットのスクリーン座標を計算
                                    target_rect = target["rect"]
                                    screen_x = target_rect.x - offset_x
                                    screen_y = target_rect.y - offset_y

                                    # マウスがターゲットの当たり判定に入っているか
                                    if pygame.Rect(screen_x, screen_y, target_rect.width, target_rect.height).collidepoint(mx, my):
                                        abnormal_condition(target, target_id, player, player_id)
                                        send_skill_effect("normal_slash", target["rect"].centerx, target["rect"].centery)

                                elif dist <= 50:
                                    abnormal_condition(target, target_id, player, player_id)
                                    send_skill_effect("normal_slash", target["rect"].centerx, target["rect"].centery)

                                player["attack_cooldown"] = max(int(30 * cool_multiplier), 1)  # 0防止

                                # 死亡処理
                                if target["hp"] <= 0:
                                    target["animation_state"] = "dead"
                                    target["animations"]["dead"].index = 0
                                    target["alive"] = False
                                    target["hp"] = 0
                                    #target["rect"].x, target["rect"].y = 1000000, 1000000
                                    print(f"Player {target_id} died")
                    if player["attack_cooldown"] > 0:
                        player["attack_cooldown"] -= 1
                if player["attack_cooldown"] > 0:
                    player["attack_cooldown"] -= 1
                # --- シールド処理 ---
                if keys[5]:
                    if not player["ShieldRecovering"] and player["ShieldGage"] >= SHIELD_COST:
                        player["isShield"] = True
                        player["ShieldGage"] -= SHIELD_COST
                        print(f"Player {player_id} activated shield")
                        if player["animation_state"] != "shield":
                            player["animation_state"] = "shield"
                            player["animations"]["shield"].index = 0
                        
                        if player["ShieldGage"] <= 0:
                            player["ShieldRecovering"] = True
                    else:
                        player["isShield"] = False
                else:
                    player["isShield"] = False
                    
                # --- ジャンプスキル ---
                if keys[6]:
                    skill = player["common"]["jump_skill"]
                    if not skill["active"] and skill["cooldown"] <= 0:
                        skill["active"] = True
                        skill["end_time"] = current_time + 5  # 効果5秒間
                        skill["cooldown"] = 1200  #1000m/s = 60(1秒で60)      つまり20秒
                        print(f"Player {player_id} activated jump skill!")
                # --- スタンスキル ---
                if keys[7]:
                    skill = player["common"]["stun"]
                    if not skill["active"] and skill["cooldown"] <= 0:
                        skill["active"] = True
                        skill["end_time"] = current_time + 3
                        skill["cooldown"] = 900
                        print(f"Player {player_id} activated stun skill")
                        stun_range = 100
                        px, py = player["rect"].center
                        for target_id, target in players_snapshot().items():
                            if target_id != player_id and target["alive"]:
                                tx, ty = target["rect"].center
                                dist = ((px - tx)**2 + (py - ty)**2)**0.5
                                if dist <= stun_range:
                                    target["common"]["stun"]["stuned"] = True
                                    send_skill_effect("stun", target["rect"].centerx, target["rect"].centery)
                                    target["common"]["stun"]["end_time"] = current_time + 3
                                    print(f"Player {target_id} stunned by player {player_id}!")
                                    
                if player["common"]["stun"]["stuned"]:
                    for target_id, target in players_snapshot().items():
                        stun_skill = target["common"]["stun"]
                        if stun_skill.get("stuned", False):  # stunedがTrueなら
                            if current_time >= stun_skill["end_time"]:
                                stun_skill["stuned"] = False
                                print(f"Player {target_id} is stuned")
                                
                # --- 回復スキル1 ---     
                if keys[8]:
                    if player["job"] == "Player":
                        skill = player["job_skill"]["heal"]
                        if not skill["active"] and skill["cooldown"] <= 0:  #healのクールタイムとか定義
                            skill["active"] = True
                            skill["end_time"] = current_time + skill["next_time"]    #0.1秒ごとに回復する
                            skill["cooldown"] = 30
                            print(f"Player {player_id} activated heal skill")
                        elif skill["healed"] and skill["active"]:
                            skill["healed"] = False
                            
                        if skill["active"]:     #ここで実行処理
                            if not skill["healed"]:
                                player["hp"] += math.floor(random.random() * skill["amount"]) + 100
                                skill["healed"] = True
                            if player["hp"] > player["maxHp"]:
                                player["hp"] = player["maxHp"]
                    else:
                        pass
                # --- 回復スキル2 ---     
                if player["job"] == "Wizard":
                    skill = player["job_skill"]["heal"]
                    if not skill["active"] and skill["cooldown"] <= 0:  #healのクールタイムとか定義
                        skill["active"] = True
                        skill["cooldown"] = 30
                        print(f"Player {player_id} activated heal skill")
                        
                    if skill["active"]:     #ここで実行処理
                        if not skill["healed"]:
                            player["hp"] += skill["amount"]
                            skill["healed"] = True
                        if player["hp"] > player["maxHp"]:
                            player["hp"] = player["maxHp"]
                    else:
                        pass
                    if skill["healed"] and skill["active"]:
                        skill["healed"] = False
                        skill["active"] = False


                # --- Claymore罠の当たり判定 ---
                for trap in traps[:]:
                    if time.time() - trap["start_time"] > trap["duration"]:
                        traps.remove(trap)
                        continue
                    for target_id, target in players_snapshot().items():
                        if target_id == trap["owner"] or not target["alive"]:
                            continue
                        dx = target["rect"].centerx - trap["x"]
                        dy = target["rect"].centery - trap["y"]
                        if dx**2 + dy**2 <= trap["radius"]**2:
                            damage = trap["damage"] // 2 if target["isShield"] else trap["damage"]
                            target["hp"] -= damage
                            send_skill_effect("claymore_trap", trap["x"], trap["y"])
                            traps.remove(trap)
                            print(f"Player {target_id} triggered a claymore and took {damage} damage.")
                            break

                   

                # --- 職業スキル1 ---
                if keys[9]:     #attackSkill関数でまとめてる
                    #60が1秒になる  重くなるから正確ではない
                    if player["job"] == "Warrior":
                        attackSkill(player, player_id, player["job_skill"]["wave_strike"], 1000)
                    elif player["job"] == "Wizard":
                        buffSkill(player, player["job_skill"]["strength_buff"], 1500, 5)                      
                    elif player["job"] == "Assassin":
                        attackSkill(player, player_id, player["job_skill"]["shadow_move"], 200)
                    elif player["job"] == "Player":
                        attackSkill(player, player_id, player["job_skill"]["create_isGod"], 0)
                    elif player["job"] == "Sniper":
                        attackSkill(player, player_id, player["job_skill"]["far_snipe"], 900)
                    
                        
                # --- 職業スキル2 ---        
                if keys[10]:
                    if player["job"] == "Warrior":
                        attackSkill(player, player_id, player["job_skill"]["chargeBoost"], 400)
                    elif player["job"] == "Wizard":
                        buffSkill(player, player["job_skill"]["resistance_buff"], 1200, 10)
                    elif player["job"] == "Assassin":
                        attackSkill(player, player_id, player["job_skill"]["criticalAttackMulti"], 400)
                    elif player["job"] == "Sniper":
                        TrapSkill(player, player_id, player["job_skill"]["claymore_trap"], 300)
                    elif player["job"] == "Berserker":
                        buffSkill(player, player["job_skill"]["boost"], 900, 20)
                
                # --- 職業スキル奥義 ---        
                if keys[11]:
                    if player["job"] == "Warrior":
                        AttackSuper(player, player_id, player["job_skill"]["all_death_damage"], 1400)
                    elif player["job"] == "Wizard":
                        AttackSuper(player, player_id, player["job_skill"]["Element_aura"], 70)
                    elif player["job"] == "Assassin":
                        AttackSuper(player, player_id, player["job_skill"]["dummy"], 600)
                    elif player["job"] == "Sniper":
                        buffSkill(player, player["job_skill"]["over_heat"], 900, 5)
                    elif player["job"] == "Berserker":
                        buffSkill(player, player["job_skill"]["berserked"], 1200, 20)

               # --- 職業スキル2ボタン押下時（初回押下で初期化） ---
                if keys[10] and player["job"] == "Assassin":
                    skill = player["job_skill"]["criticalAttackMulti"]
                    current_time = time.time()
                    if not skill.get("active", False) and skill.get("cooldown", 0) <= 0:
                        skill["active"] = True
                        skill["target_id"] = get_nearest_target(player_id, 100)
                        skill["attack_remaining"] = skill.get("hits", 3)
                        skill["interval"] = skill.get("interval", 0.35)
                        skill["next_attack_time"] = current_time
                        skill["damaged"] = skill.get("damaged", 500)
                        skill["cooldown"] = 400  # 任意クールタイム

                # --- 毎フレームサーバループで連撃処理 ---
                critical_skill = player["job_skill"].get("criticalAttackMulti")
                if critical_skill and critical_skill.get("active", False):
                    attackSkill(player, player_id, critical_skill, cooltime=400)


                if just_pressed_13:
                    current = player["attack_status"]
                    next_status = {"normal": "poison", "poison": "burn", "burn": "regeneration", "regeneration": "normal"}[current]
                    player["attack_status"] = next_status
                    print(f"Player {player_id} changed attack status to: {next_status}")

                if just_pressed_14 and player["job"] == "Wizard":
                    current = player.get("element_type", "fire")
                    next_elements = {
                        "fire": "water",
                        "water": "ice",
                        "ice": "lightning",
                        "lightning": "wind",
                        "wind": "earth",
                        "earth": "nitro",
                        "nitro": "heal",
                        "heal": "fire",
                    }
                    player["element_type"] = next_elements.get(current, "fire")
                    print(f"Player {player_id} (Wizard) changed element to: {player['element_type']}")


            # 毎フレームサーバループで呼ぶ
            player = players[player_id]
            critical_skill = player["job_skill"].get("criticalAttackMulti")
            if critical_skill and critical_skill.get("active", False):
                attackSkill(player, player_id, critical_skill, cooltime=400)


            # クールダウン管理（共通・職業スキル）
            for skill in player["common"].values():
                if skill["cooldown"] > 0 and not skill["active"]:
                    skill["cooldown"] -= 1
            
            for skill in player["job_skill"].values():
                if skill["cooldown"] > 0 and not skill["active"]:
                    skill["cooldown"] -= 1

            # スキル効果終了
            for skill_name, skill in player["common"].items():
                if skill["active"] and current_time >= skill["end_time"]:
                    skill["active"] = False



            update_buff_effects(player)



            for pid, pdata in players_snapshot().items():
                if "debuff_effects" in pdata:
                    new_effects = []
                    for effect in pdata["debuff_effects"]:
                        if current_time >= effect["end_time"]:
                            for stat in effect["multipliers"]:
                                original_key = "original_" + stat
                                if "debuff_data" in pdata and original_key in pdata["debuff_data"]:
                                    pdata[stat] = pdata["debuff_data"][original_key]
                                    del pdata["debuff_data"][original_key]
                                    print(f"Player {pid} {stat} debuff ended and restored to: {pdata[stat]}")
                        else:
                            new_effects.append(effect)
                    pdata["debuff_effects"] = new_effects

            for target_id, target in players_snapshot().items():
                for effect in ["poison", "burn", "regeneration"]:
                    status = target["job_skill"].get(effect, {})
                    if status.get("active", False):
                        if time.time() >= status.get("end_time", 0):
                            status["active"] = False
                        else:
                            source_id = status.get("source_id")  # 付与者ID
                            if source_id is None:
                                # source_id未設定なら自己消費としてtargetを使う（安全策）
                                source_id = target_id
                            source_player = players_snapshot().get(source_id)
                            if source_player is None:
                                continue  # 付与者が居なければスキップ

                            if source_player["ShieldGage"] > 5 and not source_player["ShieldRecovering"]:
                                if effect == "poison":
                                    target["hp"] -= 2
                                elif effect == "burn":
                                    target["hp"] -= 3
                                elif effect == "regeneration":
                                    target["hp"] = min(target["hp"] + 5, target["maxHp"])
                                source_player["ShieldGage"] -= 5

                                if target["hp"] <= 0:
                                    target["animation_state"] = "dead"
                                    target["animations"]["dead"].index = 0
                                    target["alive"] = False
                                    status["active"] = False
                                    target["hp"] = 0
                                    print(f"Player {target_id} died")
                            else:
                                source_player["ShieldRecovering"] = True
                                status["active"] = False

            if player["ShieldGage"] < SHIELD_GAGE:
                player["ShieldGage"] += SHIELD_COST/2
            if player["ShieldRecovering"] and player["ShieldGage"] >= 30:
                player["ShieldRecovering"] = False
                
                    
            # --- 重力処理 ---
            # --- ジャンプスキルを考慮した重力処理 ---
            if player["common"]["jump_skill"]["active"] and current_time <= player["common"]["jump_skill"]["end_time"]:
                gravity_force = GRAVITY * 0.3  # 軽くする
            else:
                gravity_force = GRAVITY
                player["common"]["jump_skill"]["active"] = False  # 時間切れでOFF

            player["vel_y"] += gravity_force
            player["rect"].y += player["vel_y"]


            if player["rect"].bottom >= HEIGHT - 150:
                player["rect"].bottom = HEIGHT - 150
                player["vel_y"] = 0
                player["on_ground"] = True
          
            handle_map_collision(player)        #位置入れ替えたら治った笑
            handle_collision(player_id)         #位置入れ替えたら治った笑

            # ゲーム状態送信（軽量化）
            game_state = {}
            for pid, pdata in players_snapshot().items():
                game_state[pid] = {
                    "x": pdata["rect"].x,
                    "y": pdata["rect"].y,
                    "job": pdata["job"],
                    "hp": pdata["hp"],
                    "maxHp": pdata["maxHp"],
                    "defense": pdata["defense"],
                    "alive": pdata["alive"],
                    "isShield": pdata["isShield"],
                    "ShieldGage": pdata["ShieldGage"],
                    "ShieldRecovering": pdata["ShieldRecovering"],
                    "animation_state": pdata["animation_state"],
                    "animation_index": pdata["animations"][pdata["animation_state"]].index,
                    "facing_right": pdata["facing_right"],
                    "attack_status": pdata.get("attack_status", "normal"),
                    "element_type": pdata.get("element_type", "fire"),

                    "skills": {
                        "common": {
                            name: {
                                "active": s["active"],
                                "cooldown": s["cooldown"]
                            } for name, s in pdata["common"].items()
                        },
                        "job": {
                            name: {
                                "active": s["active"],
                                "cooldown": s["cooldown"]
                            } for name, s in pdata["job_skill"].items()
                            if name in job_data[pdata["job"]]["skills"]  # ✅ 本来のスキルだけ送る
                        }
                    },
                    "mouse_pos": pdata["mouse_pos"],
                }
            # skill_effects を送信データに含める
            game_state["skill_effects"] = [

                e for e in skill_effects if time.time() - e["start"] < e["duration"]
            ]
            visible_traps = [
                {"x": t["x"], "y": t["y"], "radius": t["radius"]}
                for t in traps if t["owner"] == player_id
            ]
            game_state["traps"] = visible_traps



            client_socket.send(pickle.dumps(game_state))
            previous_keys = keys[:] 
    except ConnectionResetError:
        print(f"Player {player_id} disconnected unexpectedly.")
    finally:
        with players_lock:
            if player_id in players:
                del players[player_id]
        client_socket.close()
        print(f"Player {player_id} disconnected.")


# --- シールド時のダメージ計算処理
def calculate_damage_with_shield(raw_damage, target, multiplier=1.0, ignore_defense=False, min_ratio=0.1):
    # 1. ランダム変動
    variation = random.uniform(0.9, 1.1)
    damage = raw_damage * variation * multiplier

    # 2. 防御計算
    if not ignore_defense:
        def_mult = get_defense_multiplier(target)
        defense_mul = 100 / (100 + target["defense"] * def_mult)
        defense_mul = max(defense_mul, min_ratio)
        damage *= defense_mul

    # 3. 整数化前の調整
    damage = max(damage, 1.0)

    # 4. シールド処理
    if target.get("isShield") and target.get("ShieldGage", 0) > 0:
        absorb_ratio = target.get("shield_absorb_ratio", 0.5)
        absorb = damage * absorb_ratio
        hp_damage = damage - absorb

        # ShieldGage 減少と状態変化
        target["ShieldGage"] -= absorb
        if target["ShieldGage"] <= 0:
            target["ShieldGage"] = 0
            target["isShield"] = False
            target["ShieldRecovering"] = True

        return max(1, int(math.floor(hp_damage)))

    return max(1, int(math.floor(damage)))


# --- ダメージ計算処理 ---
def get_damage_multiplier(player):
    multiplier = 1.0

    # バフ
    for skill in player["job_skill"].values():
        if skill.get("buffed"):
            mults = skill.get("applied_multipliers", {})
            multiplier *= mults.get("damaged", 1.0)

    # デバフ
    for debuff in player.get("debuff_effects", []):
        if time.time() <= debuff["end_time"]:
            mults = debuff.get("multipliers", {})
            multiplier *= mults.get("damaged", 1.0)

    return multiplier


# ---　防御力のバフ処理 ---
def get_defense_multiplier(player):
    multiplier = 1.0
    for debuff in player.get("debuff_effects", []):
        if time.time() <= debuff["end_time"]:
            multiplier *= debuff["multipliers"].get("defense", 1.0)
    return multiplier


# --- 自身もしくは相手が死んだか判定 ---
def handle_death(p):
    if p["hp"] <= 0:
        p["animation_state"] = "dead"
        p["animations"]["dead"].index = 0
        p["alive"] = False
        p["hp"] = 0


# --- buff状態にし、ステータスを上げる処理 ---
def update_buff_effects(player):
    current_time = time.time()
    effects = player.get("buffed_effects", [])
    new_effects = []

    for effect in effects:
        if current_time < effect["end_time"]:
            new_effects.append(effect)
        else:
            print(f"[BUFF END] {player['job']} {effect['multipliers']}")
            if "source" in effect:
                effect["source"]["active"] = False
                effect["source"]["buffed"] = False

    if len(effects) != len(new_effects):
        player["buffed_effects"] = new_effects
        update_buffed_stats(player)


# --- buffの終了を確認しバフ以前の状態に戻す ---
def update_buffed_stats(player):
    job_stats = job_data.get(player["job"], {})
    base_damaged = job_stats.get("damaged", 1)
    base_defense = job_stats.get("defense", 1)
    base_attack_cooldown = job_stats.get("attack_cooldown", 1)

    total_multipliers = {"damaged": 1.0, "defense": 1.0, "attack_cooldown": 1.0}
    for effect in player.get("buffed_effects", []):
        for stat, multiplier in effect.get("multipliers", {}).items():
            total_multipliers[stat] *= multiplier

    player["damaged"] = int(base_damaged * total_multipliers["damaged"])
    player["defense"] = int(base_defense * total_multipliers["defense"])
    player["attack_cooldwon"] = int(base_attack_cooldown * total_multipliers["attack_cooldown"])

    print(f"[BUFF RECALC] {player['job']} damaged: {player['damaged']}, defense: {player['defense']}, attack_cooldown: {player['attack_cooldown']}")


# --- 奥義スキル管理 ---
def AttackSuper(player, player_id, skill, cooltime):
    current_time = time.time()
    multiplier = get_damage_multiplier(player)

    # Sniper専用処理：奥義時に連射モード開始
    if player["job"] == "Sniper":
        over_heat = player["job_skill"]["over_heat"]
        if not over_heat["active"] and over_heat["cooldown"] <= 0:
            over_heat.update({
                "active": True,
                "buffed": True,
                "end_time": current_time + 5,
                "cooldown": 0
            })
            print(f"Player {player_id} activated over_heat!")

    if skill["cooldown"] > 0:
        return

    for target_id, target in players_snapshot().items():
        if target_id == player_id or not target["alive"]:
            continue

        dx = player["rect"].centerx - target["rect"].centerx
        dy = player["rect"].centery - target["rect"].centery
        dist = (dx**2 + dy**2) ** 0.5

        if player["job"] == "Warrior" and dist <= 500:
            send_skill_effect("all_death_damage", target["rect"].centerx, target["rect"].centery)
            send_skill_effect("all_death_damage", player["rect"].centerx, player["rect"].centery)
            damage = calculate_damage_with_shield(skill["damaged"], target, multiplier=get_damage_multiplier(player))
            target["hp"] -= damage

            self_damage = calculate_damage_with_shield(skill["damaged"] / 1.2, player, multiplier)
            player["hp"] -= self_damage
            

        elif player["job"] == "Assassin" and abs(dx) <= 75:
            speed = job_data["Assassin"]["skills"]["dummy"]["speed"]
            direction = 1 if player["rect"].x < target["rect"].x else -1
            player["rect"].x += min(abs(dx), speed) * direction
            damage = calculate_damage_with_shield(skill["damaged"], target, multiplier=get_damage_multiplier(player))
            target["hp"] -= damage
            


        elif player["job"] == "Wizard" and abs(dx) <= 120:
            damage = calculate_damage_with_shield(skill["damaged"], target, multiplier=get_damage_multiplier(player))
            target["hp"] -= damage
            apply_element_effect(player, target, skill, player_id)
            

        elif player["job"] == "Sniper":
            over_heat = player["job_skill"]["over_heat"]
            if over_heat["active"] and current_time >= over_heat["end_time"]:
                over_heat.update({
                    "active": False,
                    "buffed": False,
                    "cooldown": max(cooltime, 900) * 2
                })
                print(f"Player {player_id} over_heat ended. Cooldown set to {over_heat['cooldown']}")


        skill["cooldown"] = cooltime
        skill["active"] = False
        handle_death(target)
        handle_death(player)


# --- 職業スキル管理 ---
def attackSkill(player, player_id, skill, cooltime):
    current_time = time.time()
    multiplier = get_damage_multiplier(player)

    # クールタイム中は何もしない
    if skill.get("cooldown", 0) > 0 and skill.get("attack_remaining", 0) <= 0:
        return

    # 発動初回処理
    if not skill.get("active", False):
        skill["active"] = True
        skill["cooldown"] = cooltime

        # Assassin: criticalAttackMulti 用
        if skill is player["job_skill"].get("criticalAttackMulti"):
            skill["attack_remaining"] = skill.get("hits", 3)
            skill["interval"] = skill.get("interval", 0.35)
            skill["next_attack_time"] = current_time
            # 最初のターゲット決定
            for tid, t in players_snapshot().items():
                if tid != player_id and t["alive"]:
                    skill["target_id"] = tid
                    break
            player["animation_state"] = "attack2"
            player["animations"]["attack2"].index = 0

    # ターゲット取得
    if skill is player["job_skill"].get("criticalAttackMulti") and skill.get("active", False):
        target_id = skill.get("target_id")
        target = players_snapshot().get(target_id)
        if not target or not target["alive"]:
            skill["active"] = False
            return

        # 攻撃タイミングチェック
        if current_time >= skill["next_attack_time"] and skill["attack_remaining"] > 0:
            dmg = skill.get("damaged", 500)
            if target.get("isShield", False):
                dmg /= 2
            target["hp"] -= dmg
            send_skill_effect("criticalAttackMulti", target["rect"].centerx, target["rect"].centery)
            player["animation_state"] = "attack2"
            player["animations"]["attack2"].index = 0
            skill["attack_remaining"] -= 1
            skill["next_attack_time"] = current_time + skill.get("interval", 0.35)

            if target["hp"] <= 0:
                target["hp"] = 0
                target["alive"] = False
                target["animation_state"] = "dead"
                target["animations"]["dead"].index = 0

        # 連撃終了後に active を解除
        if skill["attack_remaining"] <= 0:
            skill["active"] = False

    else:
        # --- 他のスキル処理 ---
        for target_id, target in players_snapshot().items():
            if target_id == player_id or not target["alive"]:
                continue

            dx = player["rect"].centerx - target["rect"].centerx
            dy = player["rect"].centery - target["rect"].centery
            dist = (dx ** 2 + dy ** 2) ** 0.5

            # Assassin shadow_move
            if skill is player["job_skill"].get("shadow_move") and dist < 800:
                dmg = calculate_damage_with_shield(skill.get("damaged", 500), target, multiplier)
                target["hp"] -= dmg
                player["rect"].x, player["rect"].y = target["rect"].x, target["rect"].y
                target["common"]["stun"].update({"stuned": True, "end_time": current_time + 0.1})
                send_skill_effect("shadow_move", player["rect"].centerx, player["rect"].centery)

            # Sniper
            elif player["job"] == "Sniper" and abs(dx) <= 2000:
                dmg = calculate_damage_with_shield(skill.get("damaged", 500), target, multiplier)
                target["hp"] -= dmg
                send_skill_effect("all_death_damage", target["rect"].centerx, target["rect"].centery)

            # Warrior
            elif player["job"] == "Warrior":
                if player["job_skill"]["chargeBoost"]["active"]:
                    speed = player["job_skill"]["chargeBoost"]["speed"]
                    direction = 1 if player["rect"].x < target["rect"].x else -1
                    player["rect"].x += min(abs(dx), speed) * direction
                    if abs(player["rect"].x - target["rect"].x) <= speed + 50:
                        dmg = calculate_damage_with_shield(skill.get("damaged", 500), target, multiplier)
                        target["hp"] -= dmg
                        send_skill_effect("charge_boost", target["rect"].centerx, target["rect"].centery)
                        player["job_skill"]["chargeBoost"]["active"] = False
                elif player["job_skill"]["wave_strike"]["active"] and abs(dx) <= 200:
                    dmg = calculate_damage_with_shield(skill.get("damaged", 500), target, multiplier)
                    target["hp"] -= dmg
                    send_skill_effect("wave_strike", target["rect"].centerx, target["rect"].centery)

            # Player
            elif player["job"] == "Player" and dist <= 1000:
                skill_god = player["job_skill"]["create_isGod"]
                skill_god["active"] = True
                target["hp"] = min(target["hp"] + 50, target["maxHp"])
                player["rect"].x, player["rect"].y = target["rect"].x, target["rect"].y
                send_skill_effect("all_death_damage", target["rect"].centerx, target["rect"].centery)
                skill_god["active"] = False

            handle_death(target)

    handle_death(player)


# --- バフスキル管理 ---
def buffSkill(player, skill, cooltime, duration):
    current_time = time.time()
    if skill["cooldown"] <= 0:
        skill["active"] = True
        skill["buffed"] = True
        skill["cooldown"] = cooltime
        skill["end_time"] = current_time + duration

        multipliers = skill.get("multipliers", {})

        if "buffed_effects" not in player:
            player["buffed_effects"] = []

        player["buffed_effects"].append({
            "end_time": skill["end_time"],
            "multipliers": multipliers,
            "source": skill
        })

        update_buffed_stats(player)
        print(f"[BUFF] {player['job']} {multipliers}")


# --- デバフスキル管理 ---
def debuffSkill(user, target, skill, cooltime, duration):
    current_time = time.time()
    if skill.get("cooldown", 0) > 0:
        return

    skill["cooldown"] = cooltime
    debuff = {
        "end_time": current_time + duration,
        "multipliers": skill.get("multipliers", {})
    }

    if "debuff_effects" not in target:
        target["debuff_effects"] = []

    target["debuff_effects"].append(debuff)
    print(f"[DEBUFF] {user['job']} → {target['job']} {debuff['multipliers']}")


# --- トラップスキル管理 ---
def TrapSkill(player, player_id, skill, cooltime, duration=10):
    current_time = time.time()

    if skill["cooldown"] > 0:
        return  # クールダウン中

    # スキル発動
    skill["active"] = True
    skill["cooldown"] = cooltime
    skill["end_time"] = current_time + duration  # 罠の有効時間（例：10秒）

    trap = {
        "x": player["rect"].centerx,
        "y": player["rect"].bottom,
        "radius": 60,
        "damage": skill["damaged"],
        "owner": player_id,
        "start_time": current_time,
        "owner": player_id,
        "duration": skill["duration"],
    }
    traps.append(trap)
    print(f"Player {player_id} set a claymore trap.")


# --- 状態異常管理 ---
def abnormal_condition(target, target_id, player, player_id):
    print(f"Player {player_id} activated punch!")
    damage = calculate_damage_with_shield(player["damaged"], target, multiplier=get_damage_multiplier(player))
    target["hp"] -= damage

    status = player.get("attack_status", "normal")
    if status == "poison":
        target["job_skill"]["poison"] = {"active": True, "cooldown": 0, "end_time": time.time() + 2, "source_id": player_id}
        print(f"Player {target_id} is poisoned!")
    elif status == "burn":
        target["job_skill"]["burn"] = {"active": True, "cooldown": 0, "end_time": time.time() + 1, "source_id": player_id}
        print(f"Player {target_id} is burned!")
    elif status == "regeneration":
        target["job_skill"]["regeneration"] = {"active": True, "cooldown": 0, "end_time": time.time() + 3, "source_id": player_id}
        print(f"Player {target_id} is regenerated!")


# --- 魔法使いスキル属性管理 ---
def apply_element_effect(player, target, skill, player_id):
    element = player.get("element_type", "fire")

    # Wizard以外はスキップ（保険）
    if player.get("job") != "Wizard":
        return

    if not target.get("alive", True):
        return
    send_skill_effect(element, target["rect"].centerx, target["rect"].centery)
    if element == "fire":
        # 小さい火ダメージを追加
        target["job_skill"]["burn"] = {"active": True, "cooldown": 0, "end_time": time.time() + 1, "source_id": player_id}
    elif element == "ice":
        # スロー効果（速度半減など、ここではスタンで代用）
        target["common"]["stun"]["stuned"] = True
        target["common"]["stun"]["end_time"] = time.time() + 1.0
    elif element == "lightning":
        # 小確率スタン
        if random.random() < 0.6:
            target["common"]["stun"]["stuned"] = True
            target["common"]["stun"]["end_time"] = time.time() + 0.5
    elif element == "water":

        pass
    elif element == "earth":
        pass
    elif element == "wind":
        # 多段HIT向き（ここでは追加1ダメージ）
        target["hp"] -= 1
    elif element == "nitro":
        # 5%の確率で大ダメージ（危険枠）
        if random.random() < 0.5:
            target["hp"] -= skill["damaged"] / 2;
    elif element == "heal":
        if player["hp"] + skill["damaged"] / 3 <= player["maxHp"]:
            player["hp"] += skill["damaged"] / 3
        else:
            player["hp"] = player["maxHp"]


# --- player_idの振り分け ---
def accept_connections():
    player_id = 0
    while True:
        client_sock, client_addr = server.accept()
        threading.Thread(target=handle_client, args=(client_sock, client_addr, player_id), daemon=True).start()
        player_id += 1


# --- メインループ ---
def main():
    threading.Thread(target=accept_connections, daemon=True).start()
    running = True
    while running:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((100, 150, 255))
        offset_x = 0
        offset_y = 0

        if game_map:
            game_map.draw(screen, offset_x, offset_y)

        for pid, pdata in players_snapshot().items():
            if pdata["alive"]:
                state = pdata.get("animation_state", "idle")
                animation = pdata["animations"].get(state, pdata["animations"]["idle"])
                sprite = animation.get_frame()
                if not pdata.get("facing_right", True):
                    sprite = pygame.transform.flip(sprite, True, False)
            
                rect = pdata["rect"]
                sprite_rect = sprite.get_rect(center=(
                    rect.x - offset_x + rect.width // 2,
                    rect.y - offset_y + rect.height // 2
                ))
                screen.blit(sprite, sprite_rect)
                draw_health_bar(screen, rect.x - offset_x, rect.y - offset_y+40, pdata["hp"], pdata["maxHp"])
                draw_shield_gage(screen, rect.x - offset_x, rect.y - offset_y+40, pdata["ShieldGage"])
                draw_name(screen, rect.x - offset_x, rect.y - offset_y+40, pid)

                if pdata["isShield"]:
                    shield_sprite = player_shields[int(pdata["ShieldGage"] / 10) % len(player_shields)]
                    screen.blit(shield_sprite, (rect.x - 5 - offset_x, rect.y - offset_y+35))
                # スキル中なら枠など表示
                # if any(skill_info.get("active", False) for skill_info in pdata["common"].values()):
                #     pygame.draw.rect(screen, (255, 255, 0), rect.inflate(10, 10), 3)
                    
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()