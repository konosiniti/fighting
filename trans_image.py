from PIL import Image

# 元のスプライトシート
input_path = "img/effects/stun.png"     # 元画像ファイル名
output_path = "img/effects/stun.png"    # 出力ファイル名

# 1フレームのサイズ（例：64×64）
frame_width = 192
frame_height = 192

# フレームの数（横2 × 縦12）
cols = 5
rows = 2
total_frames = cols * rows

# 元画像を読み込み
src_image = Image.open(input_path)

# 新しい横長画像を作成（横に24フレーム並べる）
dst_image = Image.new("RGBA", (frame_width * total_frames, frame_height))

# 順に1フレームずつ切り出して横に貼り付け
for row in range(rows):
    for col in range(cols):
        index = row * cols + col
        x = col * frame_width
        y = row * frame_height
        frame = src_image.crop((x, y, x + frame_width, y + frame_height))
        dst_image.paste(frame, (index * frame_width, 0))

# 保存
dst_image.save(output_path)

print(f"変換完了！{output_path} に保存されました。")
