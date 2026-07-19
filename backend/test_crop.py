import os
from PIL import Image, ImageDraw, ImageFont
from cropper import smart_crop

def create_test_image(path):
    """
    Creates a test image with high edge density in a specific off-center region
    to verify that the smart cropper targets the detailed region correctly.
    """
    # Create a 1000 x 1000 blank dark blue image
    img = Image.new('RGB', (1000, 1000), color=(10, 15, 30))
    draw = ImageDraw.Draw(img)
    
    # 1. Flat regions (low edge density)
    # Just simple solid colors or nothing
    
    # 2. Detailed Region: Draw some high-contrast text and geometric patterns off-center
    # Let's put the detailed area in the top-right quadrant (x=600 to 900, y=100 to 400)
    # This will test if the cropper picks the off-center detail.
    detail_box = (600, 100, 900, 400)
    
    # Background for detailed region
    draw.rectangle(detail_box, fill=(20, 30, 60))
    
    # Draw nested circles (lots of edge lines)
    for r in range(10, 140, 10):
        draw.ellipse([750 - r, 250 - r, 750 + r, 250 + r], outline=(0, 255, 255), width=2)
        
    # Save the test image
    img.save(path)
    print(f"Created test image at: {path}")

def run_test():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(test_dir, "test_input.jpg")
    output_16_9 = os.path.join(test_dir, "test_output_16_9.jpg")
    output_9_16 = os.path.join(test_dir, "test_output_9_16.jpg")
    
    create_test_image(input_path)
    
    print("\nRunning smart crop to 16:9...")
    coords_16_9 = smart_crop(input_path, output_16_9, 16/9)
    print(f"16:9 crop coords: {coords_16_9}")
    
    print("\nRunning smart crop to 9:16...")
    coords_9_16 = smart_crop(input_path, output_9_16, 9/16)
    print(f"9:16 crop coords: {coords_9_16}")
    
    # Clean up input file, leave outputs for visual check
    if os.path.exists(input_path):
        os.remove(input_path)
        
    print("\nTest run complete!")

if __name__ == "__main__":
    run_test()
