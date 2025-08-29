import pygame

pygame.init()
screen = pygame.display.set_mode((400, 400))
pygame.display.set_caption("Multi Animation Switcher")

clock = pygame.time.Clock()

# アニメーション情報クラス
class Animation:
    def __init__(self, image_path, frame_width, frame_height, num_frames):
        sheet = pygame.image.load(image_path).convert_alpha()
        self.frames = []
        for i in range(num_frames):
            rect = pygame.Rect(i * frame_width, 0, frame_width, frame_height)
            frame = sheet.subsurface(rect).copy()
            self.frames.append(frame)
        self.num_frames = num_frames
        self.index = 0

    def get_frame(self):
        frame = self.frames[self.index]
        self.index = (self.index + 1) % self.num_frames
        return frame

# アニメーションロード
animations = {
    'run': Animation("Run.png", 128, 128, 8),
    'idle': Animation("Idle.png", 128, 128, 4),  # Idle.pngは例です、4フレームだと仮定
    'jump': Animation("Jump.png", 128, 128, 10),
    'walk': Animation("Walk.png", 128, 128, 8),
    'dead': Animation("Dead.png", 128, 128, 3),
    'shield': Animation("Shield.png", 128, 128, 2),
    'attack1': Animation("Attack_1.png", 128, 128, 4),
    'attack2': Animation("Attack_2.png", 128, 128, 3),
    'attack3': Animation("Attack_3.png", 128, 128, 4),
    'hurt': Animation("Hurt.png", 128, 128, 3)
}

# デフォルトアニメーション
current_anim = animations['idle']

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                current_anim = animations['idle']
            elif event.key == pygame.K_2:
                current_anim = animations['run']
            elif event.key == pygame.K_3:
                current_anim = animations['jump']
            elif event.key == pygame.K_4:
                current_anim = animations['walk']
            elif event.key == pygame.K_5:
                current_anim = animations['dead']
            elif event.key == pygame.K_6:
                current_anim = animations['shield']
            elif event.key == pygame.K_7:
                current_anim = animations['attack1']
            elif event.key == pygame.K_8:
                current_anim = animations['attack2']
            elif event.key == pygame.K_9:
                current_anim = animations['attack3']
            elif event.key == pygame.K_0:
                current_anim = animations['hurt']
    screen.fill((30, 30, 30))

    frame = current_anim.get_frame()
    rect = frame.get_rect(center=(200, 200))
    screen.blit(frame, rect)

    pygame.display.flip()
    clock.tick(10)  # アニメーション速度

pygame.quit()
