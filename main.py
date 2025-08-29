import socket
import pygame
import pickle
import threading
import json
import copy
import time
import random

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

job_data = {
    "Warrior": {
        "hp": 4000,
        "damaged": 28,
        "skills": {
            "wave_strike": {"active": False, "damaged": 400, "cooldown": 0, "end_time": 0},
            "chargeBoost": {"active": False, "damaged": 200, "speed": 10, "cooldown": 0, "end_time": 0},
            "all_death_damage": {"active": False, "damaged": 1000, "cooldown": 0, "end_time": 0},
        }
    },
    "Healer": {
        "hp": 2200,
        "damaged": 20,
        "skills": {
            "heal": {"active": False, "healed": False, "cooldown": 0, "end_time": 0, "amount": 20},
            "strength_buff": {"active": False, "multiplier": 1.5, "target_stat": "damaged", "buffed": False, "cooldown": 0, "end_time": 0},
            "resistance_buff": {"active": False, "multiplier": 2, "target_stat": "maxHp", "buffed": False, "cooldown": 0, "end_time": 0},
            "reverse_heal": {"active": False, "damaged": 800, "cooldown": 0, "end_time": 0}
        }
    },
    "Assassin": {
        "hp": 3500,
        "damaged": 40,
        "skills": {
            "criticalAttackMulti": {"active": False, "damaged": 500, "cooldown": 0, "end_time": 0},
            "dummy" : {"active": False, "damaged": 1200, "speed": 20, "cooldown": 0, "end_time": 0},
            
        }
    },
    "Player": {
        "hp": 33000,
        "damaged": 120,
        "skills": {
            "heal": {"active": False, "healed": False, "cooldown": 0, "end_time": 0, "amount": 20000},
            "create_isGod": {"active": False, "damaged": -2000, "cooldown": 0, "end_time": 0}, 
        }
    },
    "Sniper": {
        "hp": 3000,
        "damaged": 80,
        "skills": {
            "far_snipe": {"active": False, "damaged": 700, "cooldown": 0, "end_time": 0},
            "over_heat": {"active": False, "damaged": 1, "multiplier": 0.1, "target_stat": "attack_cooldown", "buffed": False, "cooldown": 0, "end_time": 0},
        }
    },
}

def load_map(path):
    with open(path, "r") as f:
        return json.load(f)

# --- pygame初期化 ---
pygame.init()
WIDTH, HEIGHT = 992, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

def get_sprite(sheet, col, row, width, height):
    sprite = pygame.Surface((width, height), pygame.SRCALPHA)
    sprite.blit(sheet, (0, 0), pygame.Rect(col * width, row * height, width, height))
    return sprite

def create_animations():
    return {
        'run': Animation("アニメーション/Run.png", 128, 128, 8, 0.1),
        'idle': Animation("アニメーション/Idle.png", 128, 128, 4, 0.45),
        'jump': Animation("アニメーション/Jump.png", 128, 128, 10, 0.85),
        'walk': Animation("アニメーション/Walk.png", 128, 128, 8, 0.25),
        'dead': Animation("アニメーション/Dead.png", 128, 128, 3, 0.25),
        'shield': Animation("アニメーション/Shield.png", 128, 128, 2, 0.25),
        'attack1': Animation("アニメーション/Attack_1.png", 128, 128, 4, 0.01),
        'attack2': Animation("アニメーション/Attack_2.png", 128, 128, 3, 1),
        'attack3': Animation("アニメーション/Attack_3.png", 128, 128, 4, 1),
        'hurt': Animation("アニメーション/Hurt.png", 128, 128, 3, 0.25)
    }

shieldsheet = pygame.image.load("img/shield.png").convert_alpha()

all_map = ["map/field.json", "map/town.json", "map/guild.json", "map/guild2.json", "map/forest.json","map/wetland.json", "map/cave.json", "map/lava.json", "map/battle.json"]

# shieldスプライトは5フレーム分 (i=5〜1)
player_shields = [get_sprite(shieldsheet, i, 0, 50, 50) for i in range(5, 0, -1)]
player_size = (40, 115)
players = {}
SPEED = 4
JUMP_VELOCITY = -15
GRAVITY = 0.5
SHIELD_GAGE = 500
SHIELD_COST = 1
offset_x = 0
offset_y = 0
font = pygame.font.SysFont(None, 20)
HOST = '0.0.0.0'
PORT = 5050

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)

print(f"Waiting for connections on {HOST}:{PORT}...")
#selected_map = random.choice(all_map)  #ランダム用
selected_map = all_map[0]   #初期マップ
map_data = load_map(selected_map)
game_map = Map(map_data)

def draw_shield_gage(surface, x, y, gage, max_gage=500, width=40, height=5):
    ratio = gage / max_gage
    pygame.draw.rect(surface, (100, 100, 100), (x, y - 15, width, height))
    pygame.draw.rect(surface, (0, 200, 255), (x, y - 15, width * ratio, height))

def draw_health_bar(surface, x, y, hp, max_hp=100, width=40, height=5):
    ratio = hp / max_hp
    pygame.draw.rect(surface, (255, 0, 0), (x, y - 10, width, height))
    pygame.draw.rect(surface, (0, 255, 0), (x, y - 10, width * ratio, height))

def draw_name(surface, x, y, player_id, width=40, height=40):
    text_surface = font.render(f"{player_id}", True, (0, 0, 0), (255, 255, 255))
    text_rect = text_surface.get_rect()
    text_rect.center = (x + width // 2, y - 20)
    surface.blit(text_surface, text_rect)

def handle_collision(player_id):
    player_rect = players[player_id]["rect"]
    
    for other_id, other_data in players.items():
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

def handle_client(client_socket, client_address, player_id):
    print(f"Player {player_id} connected from {client_address}")
    client_socket.send(pickle.dumps(player_id))
    client_socket.send(pickle.dumps(selected_map))
    job = pickle.loads(client_socket.recv(1024))
    stats = job_data.get(job, job_data["Player"])

    player_x, player_y = 100 + player_id * 100, HEIGHT - player_size[1] - 150

    print(f"Player {player_id} selected job: {job}")

    players[player_id] = {
        "rect": pygame.Rect(player_x, player_y, *player_size),
        "vel_y": 0,
        "on_ground": True,
        "job": job,
        "damaged": stats["damaged"],
        "hp": stats["hp"],
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
        "attack_status": "normal",
        "common": {
            "jump_skill": {"active": False, "cooldown": 0, "end_time": 0},
            "stun": {"active": False, "stuned": False, "cooldown": 0, "end_time": 0},
        },
        "job_skill": copy.deepcopy(stats.get("skills", {}))
    }
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            keys = pickle.loads(data)
            player = players[player_id]
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
                if keys[4]:
                    if player["attack_cooldown"] <= 0:
                        for target_id, target in players.items():
                            if target_id != player_id and target["hp"] > 0 and target["alive"] and not player["isShield"]:
                                dx = player["rect"].centerx - target["rect"].centerx
                                dy = player["rect"].centery - target["rect"].centery
                                dist = (dx**2 + dy**2) ** 0.5
                                cool_multiplier = 1
                                if player["animation_state"] != "attack1":
                                    player["animation_state"] = "attack1"
                                    player["animations"]["attack1"].index = 0
                                    
                                # 攻撃アニメーションが終わるまで state を維持
                                if player["animation_state"].startswith("attack"):
                                    animation = player["animations"][player["animation_state"]]
                                    if animation.index >= animation.num_frames - 1:
                                        player["animation_state"] = "idle"
                                        animation.index = 0  # 念のためリセット


                                if player["job"] == "Sniper":
                                    buff = player["job_skill"].get("over_heat", {})
                                    if buff.get("buffed", False) and time.time() < buff.get("end_time", 0):
                                        cool_multiplier = buff.get("multiplier", 1.0)
                                    if dist <= 300:
                                        abnormal_condition(target, target_id, player, player_id)

                                        player["attack_cooldown"] = 30 * cool_multiplier
                                    
                                else:
                                    if dist <= 50:
                                        abnormal_condition(target, target_id, player, player_id)

                                    player["attack_cooldown"] = 30
                            if target["hp"] <= 0:
                                target["animation_state"] = "dead"
                                target["animations"]["dead"].index = 0
                                target["alive"] = False
                                target["hp"] = 0
                                #target["rect"].x, target["rect"].y = 1000000, 1000000
                                print(f"Player {target_id} died")
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
                        for target_id, target in players.items():
                            if target_id != player_id and target["alive"]:
                                tx, ty = target["rect"].center
                                dist = ((px - tx)**2 + (py - ty)**2)**0.5
                                if dist <= stun_range:
                                    target["common"]["stun"]["stuned"] = True
                                    target["common"]["stun"]["end_time"] = current_time + 3
                                    print(f"Player {target_id} stunned by player {player_id}!")
                                    
                if player["common"]["stun"]["stuned"]:
                    for target_id, target in players.items():
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
                            skill["end_time"] = current_time + 0.1    #0.1秒ごとに回復する
                            skill["cooldown"] = 30
                            print(f"Player {player_id} activated heal skill")
                        elif skill["healed"] and skill["active"]:
                            skill["healed"] = False
                            
                        if skill["active"]:     #ここで実行処理
                            if not skill["healed"]:
                                player["hp"] += skill["amount"]
                                skill["healed"] = True
                            if player["hp"] > player["maxHp"]:
                                player["hp"] = player["maxHp"]
                    else:
                        pass
                # --- 回復スキル2 ---     
                if player["job"] == "Healer":
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
                            

                # --- 職業スキル1 ---
                if keys[9]:     #attackSkill関数でまとめてる
                    #60が1秒になる  重くなるから正確ではない
                    if player["job"] == "Warrior":
                        attackSkill(player, player_id, player["job_skill"]["wave_strike"], 1000)
                    elif player["job"] == "Healer":
                        buffSkill(player, player["job_skill"]["strength_buff"], 1500, 5)                      
                    elif player["job"] == "Assassin":
                        attackSkill(player, player_id, player["job_skill"]["criticalAttackMulti"], 400)
                    elif player["job"] == "Player":
                        attackSkill(player, player_id, player["job_skill"]["create_isGod"], 0)
                    elif player["job"] == "Sniper":
                        attackSkill(player, player_id, player["job_skill"]["far_snipe"], 900)

                        
                # --- 職業スキル2 ---        
                if keys[10]:
                    if player["job"] == "Warrior":
                        attackSkill(player, player_id, player["job_skill"]["chargeBoost"], 400)
                    elif player["job"] == "Healer":
                        buffSkill(player, player["job_skill"]["resistance_buff"], 120, 7)
                    elif player["job"] == "Assassin":
                        attackSkill(player, player_id, player["job_skill"]["criticalAttackMulti"], 400)
                # --- 職業スキル奥義 ---        
                if keys[11]:
                    if player["job"] == "Warrior":
                        AttackSuper(player, player_id, player["job_skill"]["all_death_damage"], 3600)
                    elif player["job"] == "Healer":
                        attackSkill(player, player_id, player["job_skill"]["reverse_heal"], 120)
                    elif player["job"] == "Assassin":
                        AttackSuper(player, player_id, player["job_skill"]["dummy"], 600)
                    elif player["job"] == "Sniper":
                        buffSkill(player, player["job_skill"]["over_heat"], 900, 5)

                if keys[13]:
                    current = player["attack_status"]
                    next_status = {"normal": "poison", "poison": "burn", "burn": "regeneration", "regeneration": "normal"}[current]
                    player["attack_status"] = next_status
                    print(f"Player {player_id} changed attack status to: {next_status}")


            

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
            for skill_name, skill in player["job_skill"].items():
                if skill.get("active") and current_time >= skill.get("end_time", 0):
                    skill["active"] = False
                    skill["buffed"] = False     #もしかしたらバグるかも
                    target_stat = skill.get("target_stat")
                    if target_stat:
                        original = skill.get("original_" + target_stat, player.get(target_stat, 1))
                        player[target_stat] = original
                        print(f"Player {player['job']} {target_stat} restored to: {player[target_stat]}")

            for target_id, target in players.items():
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
                            source_player = players.get(source_id)
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
            player["vel_y"] += GRAVITY
            player["rect"].y += player["vel_y"]
            if player["rect"].bottom >= HEIGHT - 150:
                player["rect"].bottom = HEIGHT - 150
                player["vel_y"] = 0
                player["on_ground"] = True
          
            handle_map_collision(player)        #位置入れ替えたら治った笑
            handle_collision(player_id)         #位置入れ替えたら治った笑

            # ゲーム状態送信（軽量化）
            game_state = {}
            for pid, pdata in players.items():
                game_state[pid] = {
                    "x": pdata["rect"].x,
                    "y": pdata["rect"].y,
                    "job": pdata["job"],
                    "hp": pdata["hp"],
                    "maxHp": pdata["maxHp"],
                    "alive": pdata["alive"],
                    "isShield": pdata["isShield"],
                    "ShieldGage": pdata["ShieldGage"],
                    "ShieldRecovering": pdata["ShieldRecovering"],
                    "animation_state": pdata["animation_state"],
                    "animation_index": pdata["animations"][pdata["animation_state"]].index,
                    "facing_right": pdata["facing_right"],
                    "attack_status": pdata.get("attack_status", "normal"),

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
                                "cooldown": s["cooldown"],
                                #"buffed": s.get("buffed", False)
                            } for name, s in pdata["job_skill"].items()
                        }
                    }
                }

            client_socket.send(pickle.dumps(game_state))

    except ConnectionResetError:
        print(f"Player {player_id} disconnected unexpectedly.")
    finally:
        if player_id in players:
            del players[player_id]
        client_socket.close()
        print(f"Player {player_id} disconnected.")

def AttackSuper(player, player_id, skill, cooltime):
    current_time = time.time()
    multiplier = 1
    multiplier = 1
    if player["job"] == "Healer":
        buff = player["job_skill"].get("strength_buff", {})
        if buff.get("buffed", False):
            multiplier = buff.get("multiplier", 1)
    if player["job"] == "Sniper":
        over_heat = player["job_skill"]["over_heat"]
        if not over_heat["active"] and over_heat["cooldown"] <= 0:
            over_heat["active"] = True
            over_heat["buffed"] = True
            over_heat["end_time"] = current_time + 5  # 5秒間連射モード
            over_heat["cooldown"] = 0  # 連射中はクールなしで発動できる
            print(f"Player {player_id} activated over_heat!")

        

    if skill["cooldown"] <= 0:
        for target_id, target in players.items():
            if target_id != player_id and target["hp"] > 0 and target["alive"]:
                dx = player["rect"].centerx - target["rect"].centerx
                dy = player["rect"].centery - target["rect"].centery
                dist = (dx**2 + dy**2) ** 0.5
                    
                if player["job"] == "Warrior":
                    if dist <= 500:
                        skill["active"] = True
                        if target["isShield"]:
                            target["hp"] -= (skill["damaged"]*multiplier) / 2
                        else:
                            target["hp"] -= skill["damaged"]*multiplier
                            player["hp"] -= skill["damaged"] / 1.2
                            

                elif player["job"] == "Assassin":
                    if dist <= 75:
                        if player["rect"].x < target["rect"].x:
                            player["rect"].x += min(job_data["Assassin"]["skills"]["dummy"]["speed"], target["rect"].x - player["rect"].x)
                        else:
                            player["rect"].x += min(job_data["Assassin"]["skills"]["dummy"]["speed"]*-1, target["rect"].x + player["rect"].x)
                        skill["active"] = True
                        if target["isShield"]:
                            target["hp"] -= skill["damaged"] / 1.25
                            target["ShieldGage"] /= 2.5
                            target["isShield"] = False
                        else:
                            target["hp"] -= skill["damaged"]
                            
                    else:
                        player["hp"] -= skill["damaged"] / 1.5
                        player["common"]["stun"]["stuned"] = True
                        player["common"]["stun"]["end_time"] = current_time + 5
                        print(f'{player["common"]["stun"]["stuned"]} {player["common"]["stun"]["end_time"]}')
                
                elif player["job"] == "Sniper":
                    over_heat = player["job_skill"]["over_heat"]
                    if over_heat["active"] and current_time >= over_heat["end_time"]:
                        over_heat["active"] = False
                        over_heat["buffed"] = False
                        over_heat["cooldown"] = (cooltime if cooltime > 0 else 900) * 2  # 2倍クール
                        print(f"Player {player_id} over_heat ended. Cooldown set to {over_heat['cooldown']}")

                skill["cooldown"] = cooltime


                if target["hp"] <= 0:
                    target["animation_state"] = "dead"
                    target["animations"]["dead"].index = 0
                    target["alive"] = False
                    target["hp"] = 0
                    #target["rect"].x, target["rect"].y = 1000000, 1000000
                    print(f"Player {target_id} died")
                if player["hp"] <= 0:
                    player["animation_state"] = "dead"
                    player["animations"]["dead"].index = 0

                    player["alive"] = False
                    player["hp"] = 0
                    #player["rect"].x, player["rect"].y = 1000000, 1000000
                    print(f"Player {player_id} died")

def attackSkill(player, player_id, skill, cooltime):
    current_time = time.time()
    multiplier = 1

    if player["job"] == "Healer":
        buff = player["job_skill"].get("strength_buff", {})
        if buff.get("buffed", False):
            multiplier = buff.get("multiplier", 1)

    if skill["cooldown"] > 0:
        return  # クールダウン中

    for target_id, target in players.items():
        if target_id == player_id or not target["alive"] or target["hp"] <= 0:
            continue

        dx = player["rect"].centerx - target["rect"].centerx
        dy = player["rect"].centery - target["rect"].centery
        dist = (dx**2 + dy**2) ** 0.5

        # Assassin
        if player["job"] == "Assassin":
            if dist <= 100:
                player["common"]["stun"]["stuned"] = True
                player["common"]["stun"]["end_time"] = current_time
                if target["isShield"]:
                    target["hp"] -= (skill["damaged"] * multiplier) / 2
                else:
                    target["hp"] -= skill["damaged"] * multiplier
                skill["cooldown"] = cooltime

        # Sniper
        elif player["job"] == "Sniper":
            if dist <= 2000:
                skill["active"] = True
                damage = (skill["damaged"] * multiplier) / 2 if target["isShield"] else skill["damaged"] * multiplier
                target["hp"] -= damage
                print(f"Sniper attacked target {target_id}")
                skill["cooldown"] = cooltime

        # Warrior
        elif player["job"] == "Warrior":
            skill["active"] = True
            if dist <= 400 and player["job_skill"]["chargeBoost"]["active"]:
                speed = player["job_skill"]["chargeBoost"]["speed"]

                # プレイヤーがターゲットに向かって移動
                if player["rect"].x < target["rect"].x:
                    player["rect"].x += min(speed, target["rect"].x - player["rect"].x)
                else:
                    player["rect"].x -= min(speed, player["rect"].x - target["rect"].x)

                # 接触判定（x座標が同じ or 重なったら）
                if abs(player["rect"].x - target["rect"].x) <= speed + 50:
                    damage = (skill["damaged"] * multiplier) / 2 if target["isShield"] else skill["damaged"] * multiplier
                    target["hp"] -= damage

                    # クールタイム設定など（1回限りの処理）
                    skill["cooldown"] = cooltime
                    player["job_skill"]["chargeBoost"]["active"] = False  # スキル終了

            elif dist <= 200:
                skill["active"] = True
                if target["isShield"]:
                    target["hp"] -= (skill["damaged"] * multiplier) / 2
                else:
                    target["hp"] -= skill["damaged"] * multiplier
                skill["cooldown"] = cooltime

        # Player（特殊スキル）
        elif player["job"] == "Player":
            if dist <= 1000:
                skill_god = job_data["Player"]["skills"]["create_isGod"]
                skill_god["active"] = True
                if skill_god["active"]:
                    if target["hp"] + 50 < target["maxHp"]:
                        target["hp"] += 50
                    else:
                        target["hp"] = target["maxHp"]
                    player["rect"].x = target["rect"].x
                    player["rect"].y = target["rect"].y
                    skill_god["active"] = False
                    skill["cooldown"] = cooltime

        # ターゲット死亡処理
        if target["hp"] <= 0:
            target["animation_state"] = "dead"
            target["animations"]["dead"].index = 0
            target["alive"] = False
            target["hp"] = 0
            #target["rect"].x, target["rect"].y = 1000000, 1000000
            print(f"Player {target_id} died")

        # 自分の死亡処理
        if player["hp"] <= 0:
            player["animation_state"] = "dead"
            player["animations"]["dead"].index = 0
            player["alive"] = False
            player["hp"] = 0
            #player["rect"].x, player["rect"].y = 1000000, 1000000
            print(f"Player {player_id} died")

def buffSkill(player, skill, cooltime, duration):
    current_time = time.time()
    multiplier = skill.get("multiplier", 1)
    target_stat = skill.get("target_stat")
    if skill["cooldown"] <= 0:
        # バフ発動
        skill["active"] = True
        skill["buffed"] = True
        skill["cooldown"] = cooltime
        skill["end_time"] = current_time + duration

        # 元の値を記録（未保存なら）
        if "original_" + target_stat not in skill:
            skill["original_" + target_stat] = player.get(target_stat, 1)

        # 値を変更
        player[target_stat] = player.get(target_stat, 1) * multiplier
        print(f"Player {player['job']} {target_stat} buffed to: {player[target_stat]}")

def abnormal_condition(target, target_id, player, player_id):
    print(f"Player {player_id} activated punch!")
    if target["isShield"]:
        target["hp"] -= player["damaged"] / 2
    else:
        target["hp"] -= player["damaged"]
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
        
def accept_connections():
    player_id = 0
    while True:
        client_sock, client_addr = server.accept()
        threading.Thread(target=handle_client, args=(client_sock, client_addr, player_id), daemon=True).start()
        player_id += 1

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

        for pid, pdata in players.items():
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
                if any(skill_info.get("active", False) for skill_info in pdata["common"].values()):
                    pygame.draw.rect(screen, (255, 255, 0), rect.inflate(10, 10), 3)
                    
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
