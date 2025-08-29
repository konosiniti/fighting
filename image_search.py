import pygame
image = pygame.image.load("img/effects/stun.png")
width_frame = 5;
height_frame = 2;
#print(image.get_width(), image.get_height())
print(f"width{image.get_width()/width_frame}, height{image.get_height()/height_frame}")