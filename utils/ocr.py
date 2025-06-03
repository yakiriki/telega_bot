
import pytesseract

def extract_text_from_image(image):
    return pytesseract.image_to_string(image, lang='ukr+eng')
