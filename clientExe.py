import socket
import pygame
import pickle
import json
import os
import time
import sys
import os

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstallerが実行ファイルを展開する一時フォルダ
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# ----- Mapクラス -----
class Map:
    def __init__(self, map_data):
        self.tile_width = map_data["tilewidth"]
        self.tile_height = map_data["tileheight"]
        self.width = map_data["width"]
        self.height = map_data["height"]
        self.layers = map_data["layers"]

        self.tilesets = []
        for tileset in map_data["tilesets"]:
            image_path = os.path.join("map", os.path.basename(tileset["image"]))
            image = pygame.image.load(image_path).convert_alpha()
            columns = image.get_width() // self.tile_width
            self.tilesets.append({
                "firstgid": tileset["firstgid"],
                "image": image,
                "columns": columns
            })

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
    def __init__(self, image_path, frame_width, frame_height, num_frames, speed):
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
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update >= self.speed * 1000:
            self.index = (self.index + 1) % self.num_frames
            self.last_update = current_time
        return self.frames[self.index]


# === クライアント用エフェクトアニメーションクラス ===
class ClientEffectAnimation:
    def __init__(self, image_path, frame_width, frame_height, num_frames, speed=0.1, scale=1.0):
        sheet = pygame.image.load(image_path).convert_alpha()
        self.frames = []
        self.speed = speed
        self.frame_count = num_frames
        self.scale = scale  # ← 追加

        for i in range(num_frames):
            rect = pygame.Rect(i * frame_width, 0, frame_width, frame_height)
            frame = sheet.subsurface(rect).copy()
            if scale != 1.0:
                frame = pygame.transform.scale(frame, (int(frame_width * scale), int(frame_height * scale)))
            self.frames.append(frame)

    def get_frame(self, elapsed):
        frame_index = int(elapsed / self.speed)
        if frame_index < self.frame_count:
            return self.frames[frame_index]
        return None

#シールドのアニメーション(最後まで行ったら最後で止める)
class HoldLastFrameAnimation:
    def __init__(self, sheet_path, frame_width, frame_height, num_frames, speed, scale=1.0):
        self.sheet = pygame.image.load(sheet_path).convert_alpha()
        self.frames = []
        for i in range(num_frames):
            rect = pygame.Rect(i * frame_width, 0, frame_width, frame_height)
            frame = self.sheet.subsurface(rect).copy()
            if scale != 1.0:
                frame = pygame.transform.scale(frame, (int(frame_width * scale), int(frame_height * scale)))
            self.frames.append(frame)

        self.num_frames = num_frames
        self.speed = speed
        self.start_time = None

    def start(self):
        self.start_time = time.time()

    def get_frame(self):
        if self.start_time is None:
            return self.frames[0]
        elapsed = time.time() - self.start_time
        index = int(elapsed / self.speed)
        if index >= self.num_frames:
            return self.frames[-1]  # 最後のフレームで止まる
        return self.frames[index]


def load_map(path):
    with open(path, "r") as f:
        return json.load(f)


def draw_health_bar(surface, x, y, hp, max_hp=100, width=40, height=5):
    ratio = hp / max_hp
    pygame.draw.rect(surface, (255, 0, 0), (x, y - 10, width, height))
    pygame.draw.rect(surface, (0, 255, 0), (x, y - 10, width * ratio, height))


def draw_shield_gage(surface, x, y, gage, max_gage=500, width=40, height=5):
    ratio = max(0, min(gage / max_gage, 1))  # 0～1の範囲にクランプ
    pygame.draw.rect(surface, (100, 100, 100), (x, y - 15, width, height))  # 背景
    pygame.draw.rect(surface, (0, 200, 255), (x, y - 15, width * ratio, height))  # 青ゲージ


def draw_name(surface, x, y, player_id, width=40, height=40):
    text_surface = font.render(f"{player_id}", True, (0, 0, 0), (255, 255, 255))
    text_rect = text_surface.get_rect()
    text_rect.center = (x + width // 2, y - 25)
    surface.blit(text_surface, text_rect)


def draw_fixed_skill_ui(surface, player_skills, shield_gage=0):
    size = 30
    spacing = 10
    base_x = WIDTH - (size + spacing) * (len(player_skills) + 1) - 20
    base_y = HEIGHT - size - 20

    # 通常スキルアイコン表示
    for i, (name, skill) in enumerate(player_skills.items()):
        icon = skill_icon_images.get(name, None)
        x = base_x + i * (size + spacing)
        y = base_y
        rect = pygame.Rect(x, y, size, size)

        icon_draw = icon.copy() if icon else pygame.Surface((size, size))
        icon_draw.fill((150, 150, 150)) if icon is None else None

        cooldown = skill.get("cooldown", 0)
        icon_draw.set_alpha(100 if cooldown > 0 else 255)

        surface.blit(icon_draw, rect)

        if cooldown > 0: #pdata["skills"]["job"][""]["end_time"] > 0 or 
            #if pdata["skills"]["job"]["end_time"] > 0:
                #current_time = time.time()
                #seconds = max(1, int(current_time-skills_job["end_time"] / 60))
            #else:
            seconds = max(1, int(cooldown / 60 + 1))
            text = font.render(str(seconds), True, (255, 255, 255))
            text_rect = text.get_rect(center=rect.center)
            surface.blit(text, text_rect)
    # --- シールドアイコン + ゲージ表示 ---
    shield_icon = skill_icon_images.get("shield", None)
    shield_x = base_x + len(player_skills) * (size + spacing)
    shield_y = base_y
    shield_rect = pygame.Rect(shield_x, shield_y, size, size)

    icon_draw = shield_icon.copy() if shield_icon else pygame.Surface((size, size))
    icon_draw.fill((100, 100, 100)) if shield_icon is None else None

    surface.blit(icon_draw, shield_rect)

    # シールドゲージ描画（下に青いバーを表示）
    gauge_ratio = max(0, min(shield_gage / 500.0, 1))  # 想定：最大500
    bar_height = 5
    bar_width = int(size * gauge_ratio)

    bar_rect = pygame.Rect(shield_x, shield_y + size - bar_height + 10, bar_width, bar_height)
    pygame.draw.rect(surface, (0, 200, 255), bar_rect)


def draw_skill_effects(surface, effect_animations, client_skill_effects, offset_x, offset_y):
    current_time = time.time()
    for effect in client_skill_effects:
        elapsed = current_time - effect["start"]
        anim = effect_animations.get(effect["type"])
        if not anim:
            continue
        frame = anim.get_frame(elapsed)
        if frame:
            rect = frame.get_rect(center=(effect["x"] - offset_x, effect["y"] - offset_y))
            surface.blit(frame, rect)


def get_sprite(sheet, col, row, width, height):
    sprite = pygame.Surface((width, height), pygame.SRCALPHA)
    sprite.blit(sheet, (0, 0), pygame.Rect(col * width, row * height, width, height))
    return sprite


def select_job():
    selecting = True
    selected_job = None
    font_large = pygame.font.SysFont(None, 40)
    options = ["Warrior", "Wizard", "Assassin", "Player", "Sniper", "Berserker", "Gambler"]
    while selecting:
        screen.fill((50, 50, 100))
        title = font_large.render("職業を選んでください", True, (255, 255, 255))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 100))
        for i, job in enumerate(options):
            color = (255, 255, 0) if selected_job == i else (255, 255, 255)
            text = font_large.render(f"{i+1}: {job}", True, color)
            screen.blit(text, (WIDTH//2 - text.get_width()//2, 200 + i*60))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.KEYDOWN:
                if event.key in [pygame.K_1, pygame.K_KP1]:
                    selected_job = 0
                    selecting = False
                elif event.key in [pygame.K_2, pygame.K_KP2]:
                    selected_job = 1
                    selecting = False
                elif event.key in [pygame.K_3, pygame.K_KP3]:
                    selected_job = 2
                    selecting = False
                elif event.key in [pygame.K_4, pygame.K_KP4]:
                    selected_job = 3
                    selecting = False
                    
                elif event.key in [pygame.K_5, pygame.K_KP5]:
                    selected_job = 4 
                    selecting = False
                elif event.key in [pygame.K_6, pygame.K_KP6]:
                    selected_job = 5
                    selecting = False
                elif event.key in [pygame.K_7, pygame.K_KP7]:
                    selected_job = 6
                    selecting = False

    return options[selected_job]


damage_texts = []  # (x, y, text, timer)
# ----- Pygame初期化 -----
pygame.init()
WIDTH, HEIGHT = 992, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Multiplayer Client")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 20)

# サーバー接続情報
#HOST = '180.12.140.4'  # 必要に応じて変更
HOST = '127.0.0.1'
#HOST = '192.168.35.52'
#HOST = '192.168.33.10'
#HOST = '192.168.33.28'
PORT = 5050

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

print("① ID受信待ち...")
my_player_id = pickle.loads(client.recv(16))
print(f"→ ID受信完了: {my_player_id}")

print("② マップ名受信待ち...")
map_data_name = pickle.loads(client.recv(1024))
print(f"→ マップ名受信: {map_data_name}")

print("③ 職業選択へ")
selected_job = select_job()
print(f"→ 選択された職業: {selected_job}")

print("④ 職業を送信中...")
client.send(pickle.dumps(selected_job))
print("→ 職業送信完了")


map_data = load_map(map_data_name)
game_map = Map(map_data)
prev_hps = {}  # プレイヤーごとの前のHP記録
font_large = pygame.font.SysFont(None, 30)


element_effects = [
    "fire", "water", "lightning",
    "earth", "wind", "ice"
]

effect_animations = {
    "stun": ClientEffectAnimation(resource_path("img/effects/stun.png"), 192, 192, 10, 0.05),
    "wave_strike": ClientEffectAnimation(resource_path("img/effects/wave_strike.png"), 64, 64, 1, 0.08),
    "all_death_damage": ClientEffectAnimation(resource_path("img/effects/all_death_damage.png"), 120, 120, 7, 0.08),
    "normal_slash": ClientEffectAnimation(resource_path("img/effects/normal_slash.png"), 120, 120, 5, 0.08),
    "criticalAttackMulti": ClientEffectAnimation(resource_path("img/effects/criticalAttackMulti.png"), 640, 480, 24, 0.08, scale=0.3),
    "shadow_move": ClientEffectAnimation(resource_path("img/effects/shadow_move.png"), 320, 120, 8, 0.1),
    "charge_boost": ClientEffectAnimation(resource_path("img/effects/charge_boost.png"), 120, 120, 5, 0.08),
    "claymore_trap": ClientEffectAnimation(resource_path("img/effects/claymore_trap.png"), 320, 120, 6, 0.1),
    "Element_aura": ClientEffectAnimation(resource_path("img/effects/Element_aura.png"), 120, 120, 8, 0.1),
    **{name: ClientEffectAnimation(resource_path(f"img/effects/{name}.png"), 120, 120, 8, 0.1) for name in element_effects}
}




# スキルアイコンの読み込み
skill_icon_images = {}
icon_names = [
    "shield", "jump_skill", "stun",
    "wave_strike", "chargeBoost", "all_death_damage",
    "strength_buff", "resistance_buff", "Element_aura",
    "shadow_move", "criticalAttackMulti", "dummy",
    "heal", "create_isGod",
    "far_snipe", "claymore_trap", "over_heat",
    "boost", "berserked",
    "poison_status", "burn_status", "regeneration_status"
]
# このリストをどこかに追加（プレイヤー辞書の外）
traps = []

for name in icon_names:
    try:
        path = os.path.join("icons", f"{name}.png")
        skill_icon_images[name] = pygame.image.load(resource_path(path)).convert_alpha()
        print("アイコン読み込み成功")
    except Exception as e:
        print(f"スキルアイコン読み込み失敗: {name} -> {path} : {e}")
        skill_icon_images[name] = pygame.Surface((32, 32))
        skill_icon_images[name].fill((100, 100, 100))

# 状態異常アイコンの読み込み
status_icon_images = {}


status_names = [
    "normal", "poison", "burn", "regeneration"
]
for name in status_names:
    try:
        path = os.path.join("icons", f"{name}_status.png")
        status_icon_images[name] = pygame.image.load(resource_path(path)).convert_alpha()
    except Exception as e:
        print(f"状態異常アイコン読み込み失敗: {name} -> {path} : {e}")
        status_icon_images[name] = pygame.Surface((32, 32))
        status_icon_images[name].fill((150, 0, 0))

#画像できるまで色で代用
element_colors = {
    "fire": (255, 60, 0),
    "water": (0, 120, 255),
    "ice": (150, 255, 255),
    "lightning": (255, 255, 0),
    "wind": (100, 255, 100),
    "earth": (150, 100, 50),
    "nitro": (255, 0, 255),
    "heal": (0, 255, 0),
}


# element_icons = {
#     "fire": pygame.image.load("img/elements/fire.png").convert_alpha(),
#     "water": pygame.image.load("img/elements/water.png").convert_alpha(),
#     "ice": pygame.image.load("img/elements/ice.png").convert_alpha(),
#     "lightning": pygame.image.load("img/elements/lightning.png").convert_alpha(),
#     "wind": pygame.image.load("img/elements/wind.png").convert_alpha(),
#     "earth": pygame.image.load("img/elements/earth.png").convert_alpha(),
#     "nitro": pygame.image.load("img/elements/nitro.png").convert_alpha(),
# }

# 初期化
shield_animations = {}

SHIELD_GAGE = 50


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


player_size = (40, 105)
players = {}
offset_x = 0
offset_y = 0
my_facing_right = True
animations = create_animations()
shield_anim_started = False
respawn_requested = False
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = [
        pygame.key.get_pressed()[pygame.K_LEFT],
        pygame.key.get_pressed()[pygame.K_RIGHT],
        pygame.key.get_pressed()[pygame.K_UP],
        pygame.key.get_pressed()[pygame.K_DOWN],
        pygame.key.get_pressed()[pygame.K_SPACE],
        pygame.key.get_pressed()[pygame.K_s],
        pygame.key.get_pressed()[pygame.K_LSHIFT],
        pygame.key.get_pressed()[pygame.K_j],
        pygame.key.get_pressed()[pygame.K_h],
        pygame.key.get_pressed()[pygame.K_k],
        pygame.key.get_pressed()[pygame.K_l],
        pygame.key.get_pressed()[pygame.K_g],
        pygame.key.get_pressed()[pygame.K_r],
        pygame.key.get_pressed()[pygame.K_z],
        pygame.key.get_pressed()[pygame.K_m],
    ]
    keys[12] = respawn_requested

    try:
        mouse_pos = pygame.mouse.get_pos()
        send_data = {
            "keys": keys,
            "mouse_pos": mouse_pos
        }
        client.send(pickle.dumps(send_data))
        game_state = client.recv(8192)

        if game_state:
            full_state = pickle.loads(game_state)
            traps = full_state.get("traps", [])

            players = {k: v for k, v in full_state.items() if isinstance(k, int)}
            client_skill_effects = full_state.get("skill_effects", [])

            for pid in players:
                if "animations" not in players[pid]:
                    pass
                    #players[pid]["animations"] = create_animations()
    except Exception as e:
        print(f"通信エラー: {e}")
        break

    # --- オフセット（カメラ位置）計算 ---
    if my_player_id in players:
        my_x = players[my_player_id]["x"]
        my_y = players[my_player_id]["y"]

        offset_x = my_x - WIDTH // 2 + player_size[0] // 2
        offset_y = my_y - HEIGHT // 2 + player_size[1] // 2

        max_offset_x = game_map.width * game_map.tile_width - WIDTH
        max_offset_y = game_map.height * game_map.tile_height - HEIGHT

        offset_x = max(0, min(offset_x, max_offset_x))
        offset_y = max(0, min(offset_y, max_offset_y))
    else:
        offset_x = 0
        offset_y = 0

    screen.fill((0, 0, 0))
    game_map.draw(screen, offset_x, offset_y)

    # トラップ描画（円 or スプライト）
    for trap in traps:
        pygame.draw.circle(screen, (255, 100, 0), (trap["x"] - offset_x, trap["y"] - offset_y), trap["radius"], 2)


    for player_id, pdata in players.items():
        x = pdata["x"]
        y = pdata["y"]
        hp = pdata["hp"]
        maxHp = pdata["maxHp"]
        defense = pdata["defense"]
        alive = pdata["alive"]
        isShield = pdata["isShield"]
        shieldGage = pdata["ShieldGage"]
        can_use_shield = pdata["ShieldRecovering"]
        skills_common = pdata["skills"]["common"]
        skills_job = pdata["skills"]["job"]
        status = pdata.get("attack_status", "normal")
        

        skills = {**skills_common, **skills_job}

        # HP変化によるダメージテキスト
        prev_hp = prev_hps.get(player_id, hp)
        if hp < prev_hp:
            damage_texts.append([x - offset_x, y - offset_y, f"-{prev_hp - hp}", (255, 0, 0), 60])
        elif hp > prev_hp:
            damage_texts.append([x - offset_x, y - offset_y, f"+{hp - prev_hp}", (0, 255, 0), 60])
        prev_hps[player_id] = hp

        if alive:
            state = pdata.get("animation_state", "idle")
            index = pdata.get("animation_index", 0)

            #sprite = pdata["animations"][state].frames[index]
            sprite = animations[state].frames[index]
            if not pdata.get("facing_right", True):
                sprite = pygame.transform.flip(sprite, True, False)

            sprite_rect = sprite.get_rect(center=(
                x - offset_x + player_size[0] // 2,
                y - offset_y + player_size[1] // 2
            ))
            screen.blit(sprite, sprite_rect)

            # --- playerの上にstatusを表示 ---
            if status in status_icon_images:
                icon = status_icon_images[status]
                icon_rect = icon.get_rect(center=(x - offset_x + 20, y - offset_y - 30))
                screen.blit(icon, icon_rect)


            if isShield:
                # プレイヤーごとのアニメーションがなければ生成
                if player_id not in shield_animations:
                    anim = HoldLastFrameAnimation(
                        resource_path("img/effects/shield.png"),
                        frame_width=192,
                        frame_height=192,
                        num_frames=16,
                        speed=0.05
                    )
                    anim.start()
                    shield_animations[player_id] = anim

                shield_frame = shield_animations[player_id].get_frame()
                if shield_frame:
                    screen.blit(shield_frame, (x - offset_x - 60, y - offset_y - 20))
            else:
                # シールド解除されたらアニメーションを削除
                if player_id in shield_animations:
                    del shield_animations[player_id]


            draw_health_bar(screen, x - offset_x, y - offset_y+40, hp, maxHp)
            draw_shield_gage(screen, x - offset_x, y - offset_y + 40, shieldGage, max_gage=500)
            draw_name(screen, x - offset_x, y - offset_y+40, player_id)


            # 属性カラー表示（Wizard限定）
            if pdata["job"] == "Wizard":
                elem_type = pdata.get("element_type", "fire")
                color = element_colors.get(elem_type, (255, 255, 255))  # デフォルト白
                center_x = x - offset_x + player_size[0] // 2
                center_y = y - offset_y - 10  # 少し上に表示
                pygame.draw.circle(screen, color, (center_x, center_y), 8)  # 直径16pxの丸




            if any(skill_info.get("active", False) for skill_info in skills.values()):
                pygame.draw.rect(screen, (255, 255, 0), sprite_rect.inflate(10, 10), 3)

            for dt in damage_texts[:]:
                dx, dy, text, color, timer = dt
                damage_surface = font_large.render(text, True, color)
                screen.blit(damage_surface, (dx, dy - (60 - timer)))
                dt[4] -= 1
                if dt[4] <= 0:
                    damage_texts.remove(dt)

            if player_id == my_player_id:
                draw_fixed_skill_ui(screen, skills, pdata.get("ShieldGage", 0))

        draw_skill_effects(screen, effect_animations, client_skill_effects, offset_x, offset_y)

        # リスポーンボタン
        if player_id == my_player_id and not alive:
            respawn_button_rect = pygame.Rect(WIDTH // 2 - 60, HEIGHT // 2 - 20, 120, 40)
            pygame.draw.rect(screen, (200, 0, 0), respawn_button_rect)
            text = font.render("respawn", True, (255, 255, 255))
            text_rect = text.get_rect(center=respawn_button_rect.center)
            screen.blit(text, text_rect)
            mouse = pygame.mouse.get_pos()
            click = pygame.mouse.get_pressed()
            if respawn_button_rect.collidepoint(mouse) and click[0]:
                respawn_requested = True
                keys[12] = True
                print('リスポーン申請中...')


    pygame.display.flip()
    clock.tick(60)

client.close()
pygame.quit()