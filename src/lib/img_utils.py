#! coding: utf-8
# pylint: disable-msg=W0311, W0621
import Image
import ImageDraw
import ImageFont
import ImageEnhance
from StringIO import StringIO
from mimemagic import from_buffer as mimetype

MAX_WIDTH = 1000  # pixels

def reduce_opacity(img, opacity):
  """returns an image with reduced opacity"""
  assert opacity >= 0 and opacity <= 1
  if img.mode != 'RGBA':
    img = img.convert('RGBA')
  else:
    img = img.copy()
  alpha = img.split()[3]
  alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
  img.putalpha(alpha)
  return img


def watermark(img, mark, position, opacity=1):
  """adds a watermark to an image"""
  if opacity < 1:
      mark = reduce_opacity(mark, opacity)
  if img.mode != 'RGBA':
      img = img.convert('RGBA')
  # create a transparent layer the size of the image and draw the
  # watermark in that layer.
  layer = Image.new('RGBA', img.size, (0,0,0,0))
  if position == 'top-right':
      layer.paste(mark, (img.size[0] - mark.size[0] - 3, 3))
  else:
      layer.paste(mark, position)
  # composite the watermark with the layer
  return Image.composite(layer, img, layer)


def add_logo(img, logo=None):
  """ add logo to image object, return an image object """
  enbac_logo = open(logo)
  mark = Image.open(enbac_logo)
  output = watermark(img, mark, 'top-right')
  enbac_logo.close()
  return output.convert("RGB")


def txt2img(text, background="#ffffff", foreground="#000000",
            font="resources/DejaVuSansCondensed.ttf",
            font_size=14, offset=(5, 5, 1.5)):
  try:
    text = unicode(text, 'utf-8')
  except UnicodeDecodeError:
    pass
  fnt = ImageFont.truetype(font, font_size)
  width, height = fnt.getsize(text)
  size = (width + offset[0] * 2, height + int(offset[1] * 2))
  img = Image.new('RGBA', size, background)
  draw = ImageDraw.Draw(img)
  draw.fontmode = "0"
  draw.text((offset[0], offset[1]), text, font=fnt, fill=foreground)
  return img


def is_image(filedata):
  res = mimetype(filedata[:1024], mime=True)
  if res.startswith("image"):
    return True
  return False


def thumb_w(filedata, width):
  """Make thumbnail with white background, ratio fixed by origin.
  Return a file object"""
  if not filedata:
    return None

  if not is_image(filedata):
    return None

  try:
    img_fp = StringIO(filedata)
    output = StringIO()

    img = Image.open(img_fp)
    img_format = img.format
    if img_format not in ["BMP", "GIF", "PNG", "PPM", "JPEG"]:
      return None

    if img_format != 'PNG' and img.mode != "RGB":
      img = img.convert("RGB")

    height = int(round(width * float(img.size[1]) / img.size[0]))
    img = img.resize((width, height), Image.ANTIALIAS)

    if img_format == "GIF":
      img = img.convert("P", dither=Image.NONE, palette=Image.ADAPTIVE)

    img.save(output, img_format, quality=90)
    filedata = output.getvalue()
    return filedata
  except SystemError:
    return None
  except (IOError, IndexError, SyntaxError, MemoryError):
    return False
  finally:
    img_fp.close()
    output.close()


def thumb_wl(filedata, width):
  """ Make thumbnail with white background, if height > 2 * width -> crop.
  Return a file object"""
  if not filedata:
    return None

  if not is_image(filedata):
    return None

  try:
    img_fp = StringIO(filedata)
    output = StringIO()

    img = Image.open(img_fp)

    img_format = img.format
    if img_format not in ["BMP", "GIF", "PNG", "PPM", "JPEG"]:
      return None

    if img_format != 'PNG' and img.mode != "RGB":
      img = img.convert("RGB")
    height = int(round(width * float(img.size[1]) / img.size[0]))
    img = img.resize((width, height), Image.ANTIALIAS)

    if img.size[1] / img.size[0] >= 2:
      # crop image, put box in center of image
      left = 0
      right = img.size[0]
      upper = img.size[1] / 2 - width
      lower = img.size[1] / 2 + width
      img = img.crop((left, upper, right, lower))

    if img_format == "GIF":
      img = img.convert("P", dither=Image.NONE, palette=Image.ADAPTIVE)

    img.save(output, img_format, quality=90)
    filedata = output.getvalue()
    return filedata
  except SystemError:
    return None
  except (IOError, IndexError, SyntaxError, MemoryError):   # truncated image
    return False
  finally:
    img_fp.close()
    output.close()
    
    
def thumb_h(filedata, height):
  """Make thumbnail with white background, ratio fixed by origin"""
  if not filedata:
    return None

  if not is_image(filedata):
    return None

  try:
    img_fp = StringIO(filedata)
    output = StringIO()

    img = Image.open(img_fp)
    img_format = img.format
    if img_format not in ["BMP", "GIF", "PNG", "PPM", "JPEG"]:
      return None

    if img_format != 'PNG' and img.mode != "RGB":
      img = img.convert("RGB")

    print img.size
    width = int(round(height * float(img.size[0]) / img.size[1]))
    print width
    print height
    img = img.resize((width, height), Image.ANTIALIAS)

    if img_format == "GIF":
      img = img.convert("P", dither=Image.NONE, palette=Image.ADAPTIVE)

    img.save(output, img_format, quality=90)
    filedata = output.getvalue()
    return filedata
  except SystemError:
    return None
  except (IOError, IndexError, SyntaxError, MemoryError):
    return False
  finally:
    img_fp.close()
    output.close()




def zoom(filedata, x, y):
  '''Downsample the image.
   @param filedata: binary image
   @param x: output width
   @param y: output height
   
   !!! NOTE: phải fix lỗi làm tròn số gây lệch 1px trong 1 số trường hợp khi sử
   dụng hàm .thumbnail() - xem thêm trong file INSTALL.rst
   '''
  if not filedata:
    return None

  if not is_image(filedata):
    return None

  img_fp = StringIO(filedata)
  output = StringIO()
  try:
    img = Image.open(img_fp)
    
    if img.size[0] > MAX_WIDTH * 5:
      return False
    
    img_format = img.format
    if img_format not in ["BMP", "GIF", "PNG", "PPM", "JPEG"]:
      return None

    size = (x, y)

    img_ratio = float(img.size[0]) / img.size[1]

    # resize but constrain proportions?
    if x == 0.0:
      x = y * img_ratio
    elif y == 0.0:
      y = x / img_ratio

    thumb_ratio = float(x) / y
    x = int(round(x)); y = int(round(y))

    if(img_ratio > thumb_ratio):
      c_width = int(round(x * img.size[1] / y))
      c_height = img.size[1]
      origin_x = int(round(img.size[0] / 2 - c_width / 2))
      origin_y = 0
    else:
      c_width = img.size[0]
      c_height = int(round(y * img.size[0] / x))
      origin_x = 0
      origin_y = int(round(img.size[1] / 2 - c_height / 2))

    crop_box = (origin_x, origin_y, origin_x + c_width, origin_y + c_height)
    try:
      img = img.crop(crop_box)
    except KeyboardInterrupt: #SystemError:
      return None
    img.thumbnail([x, y], Image.ANTIALIAS)

    if img_format != 'PNG' and img.mode != "RGB":
      img = img.convert("RGB")

    img.thumbnail(size, Image.ANTIALIAS)
    
    # enlarge if thumbnail image is smaller than size requested
    if img.size[0] != x:
      img = img.resize([x, y], Image.ANTIALIAS)
    
    if img_format == "GIF":
      img = img.convert("P", dither=Image.NONE, palette=Image.ADAPTIVE)

    img.save(output, img_format, quality=93)
    filedata = output.getvalue()
    return filedata
  except (IOError, IndexError, SyntaxError, MemoryError):
    return False
  finally:
    img_fp.close()
    output.close()
    del img_fp
    del output  
