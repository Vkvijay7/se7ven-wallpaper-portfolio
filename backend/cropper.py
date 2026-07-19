import os
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

def smart_crop(image_path, output_path, target_ratio, center_bias=0.25, upscale="4k", fit="blur", prompt=""):
    """
    Processes the image at image_path to match the target_ratio (width/height).
    Saves the output image to output_path.
    
    Supports five fit modes:
    - 'ai': (New Premium) Re-generates a brand new wallpaper in native 16:9 or 9:16
           aspect ratio using Pollinations AI based on the image description/title prompt.
           Fails back gracefully to 'expand' if the generator is offline.
    - 'expand': Center the sharp original image (no stretching, no cropping)
                and fill the empty side panels with a mirrored, blurred version of the
                border pixels, smoothly blended using a progressive shadow gradient.
    - 'blur': Center the sharp original image and fill the sides with a darkened,
              heavily blurred version of the entire image.
    - 'stretch': Squeeze/stretch the entire image to fit the aspect ratio.
    - 'crop': Perform edge-density smart cropping.
    """
    img = Image.open(image_path)
    W, H = img.size
    
    # 1. Determine target dimensions based on upscale setting
    if target_ratio > 1: # Desktop
        target_w = 3840 if upscale == "4k" else 7680 if upscale == "8k" else int(H * target_ratio)
        target_h = 2160 if upscale == "4k" else 4320 if upscale == "8k" else H
    else: # Mobile
        target_w = 2160 if upscale == "4k" else 4320 if upscale == "8k" else W
        target_h = 3840 if upscale == "4k" else 7680 if upscale == "8k" else int(W / target_ratio)

    try:
        resampling = Image.Resampling.LANCZOS
    except AttributeError:
        resampling = Image.LANCZOS

    # 2. FIT MODE: AI GENERATIVE RE-CREATION (16:9 or 9:16 native AI generation)
    if fit == "ai":
        import requests
        import urllib.parse
        
        # Build prompt from descriptive text
        p_text = prompt.strip() if prompt else ""
        if not p_text or len(p_text) < 5:
            # Fallback extract query name from file path
            p_text = os.path.basename(image_path).replace("original_", "").split("_")[0]
            if not p_text or p_text == "image":
                p_text = "stunning illustration"
                
        # Remove hashtags and cleanup
        p_clean = " ".join([word for word in p_text.split() if not word.startswith("#")])
        p_clean = p_clean.replace("Pinterest Image", "").strip()
        if not p_clean:
            p_clean = "stunning digital wallpaper art"
            
        if target_ratio > 1: # Desktop 16:9
            ai_prompt = f"{p_clean}, 16:9 aspect ratio wallpaper, highly detailed digital art, anime style, 4k"
            req_w, req_h = 1024, 576
        else: # Mobile 9:16
            ai_prompt = f"{p_clean}, 9:16 aspect ratio portrait wallpaper, highly detailed digital art, anime style, 4k"
            req_w, req_h = 576, 1024
            
        encoded_prompt = urllib.parse.quote(ai_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={req_w}&height={req_h}&nologo=true&private=true"
        
        print(f"Calling Pollinations AI for native crop re-generation: {url}")
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                temp_path = output_path + ".temp.jpg"
                with open(temp_path, "wb") as f:
                    f.write(response.content)
                
                # Load image, scale to exact target dimensions and save
                ai_img = Image.open(temp_path)
                ai_img = ai_img.resize((target_w, target_h), resampling)
                
                # Apply high-fidelity sharpening
                try:
                    ai_img = ai_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
                except:
                    pass
                    
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                ai_img.save(output_path, quality=95)
                
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                    
                return 0, 0, W, H
            else:
                print(f"Pollinations AI returned non-200 code: {response.status_code}. Falling back to expand padding.")
        except Exception as e:
            print(f"Error calling Pollinations AI: {e}. Falling back to expand padding.")
            
        # Fall back to expand if AI generation fails
        fit = "expand"

    # 3. FIT MODE: AI SMART EXPAND (Reflected mirror padding & soft shadow seam blending)
    if fit == "expand":
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        orig_ratio = W / H
        target_canvas_ratio = target_w / target_h
        
        if target_ratio > 1:
            # Desktop 16:9: Original is vertical, scale height to match target_h
            scaled_h = target_h
            scaled_w = int(target_h * orig_ratio)
            sharp_img = img.resize((scaled_w, scaled_h), resampling)
            
            # Place sharp image in center of canvas
            offset_x = (target_w - scaled_w) // 2
            
            # Left padding: Mirror the left boundary of the sharp image
            pad_w = offset_x
            if pad_w > 0:
                left_crop_w = min(pad_w, sharp_img.width)
                left_part = sharp_img.crop((0, 0, left_crop_w, target_h))
                left_mirror = left_part.transpose(Image.FLIP_LEFT_RIGHT)
                
                if left_mirror.width < pad_w:
                    left_mirror = left_mirror.resize((pad_w, target_h), resampling)
                
                left_mirror = left_mirror.filter(ImageFilter.GaussianBlur(radius=15))
                left_mirror = ImageEnhance.Brightness(left_mirror).enhance(0.65)
                canvas.paste(left_mirror, (0, 0))
                
            # Right padding: Mirror the right boundary of the sharp image
            if pad_w > 0:
                right_crop_w = min(pad_w, sharp_img.width)
                right_part = sharp_img.crop((sharp_img.width - right_crop_w, 0, sharp_img.width, target_h))
                right_mirror = right_part.transpose(Image.FLIP_LEFT_RIGHT)
                
                if right_mirror.width < pad_w:
                    right_mirror = right_mirror.resize((pad_w, target_h), resampling)
                    
                right_mirror = right_mirror.filter(ImageFilter.GaussianBlur(radius=15))
                right_mirror = ImageEnhance.Brightness(right_mirror).enhance(0.65)
                canvas.paste(right_mirror, (target_w - pad_w, 0))
                
            # Paste the sharp centered image on top
            canvas.paste(sharp_img, (offset_x, 0))
            
            # Create progressive vertical black shadow gradient mask
            shadow_w = 40
            shadow = Image.new("RGBA", (shadow_w, target_h), (0, 0, 0, 0))
            for x in range(shadow_w):
                alpha = int(220 * (1.0 - (x / shadow_w)))
                for y in range(target_h):
                    shadow.putpixel((x, y), (0, 0, 0, alpha))
            
            canvas.paste(shadow, (offset_x - shadow_w, 0), shadow)
            right_shadow = shadow.transpose(Image.FLIP_LEFT_RIGHT)
            canvas.paste(right_shadow, (offset_x + scaled_w, 0), right_shadow)
            
        else:
            # Mobile 9:16: Original is wider than target frame, scale width to match target_w
            scaled_w = target_w
            scaled_h = int(target_w / orig_ratio)
            sharp_img = img.resize((scaled_w, scaled_h), resampling)
            
            # Place sharp image in center of canvas
            offset_y = (target_h - scaled_h) // 2
            
            # Top padding: Mirror the top boundary of the sharp image
            pad_h = offset_y
            if pad_h > 0:
                top_crop_h = min(pad_h, sharp_img.height)
                top_part = sharp_img.crop((0, 0, target_w, top_crop_h))
                top_mirror = top_part.transpose(Image.FLIP_TOP_BOTTOM)
                
                if top_mirror.height < pad_h:
                    top_mirror = top_mirror.resize((target_w, pad_h), resampling)
                    
                top_mirror = top_mirror.filter(ImageFilter.GaussianBlur(radius=15))
                top_mirror = ImageEnhance.Brightness(top_mirror).enhance(0.65)
                canvas.paste(top_mirror, (0, 0))
                
            # Bottom padding: Mirror the bottom boundary of the sharp image
            if pad_h > 0:
                bottom_crop_h = min(pad_h, sharp_img.height)
                bottom_part = sharp_img.crop((0, sharp_img.height - bottom_crop_h, target_w, sharp_img.height))
                bottom_mirror = bottom_part.transpose(Image.FLIP_TOP_BOTTOM)
                
                if bottom_mirror.height < pad_h:
                    bottom_mirror = bottom_mirror.resize((target_w, pad_h), resampling)
                    
                bottom_mirror = bottom_mirror.filter(ImageFilter.GaussianBlur(radius=15))
                bottom_mirror = ImageEnhance.Brightness(bottom_mirror).enhance(0.65)
                canvas.paste(bottom_mirror, (0, target_h - pad_h))
                
            # Paste sharp center image
            canvas.paste(sharp_img, (0, offset_y))
            
            # Horizontal seam shadows
            shadow_h = 40
            shadow = Image.new("RGBA", (target_w, shadow_h), (0, 0, 0, 0))
            for y in range(shadow_h):
                alpha = int(220 * (1.0 - (y / shadow_h)))
                for x in range(target_w):
                    shadow.putpixel((x, y), (0, 0, 0, alpha))
                    
            canvas.paste(shadow, (0, offset_y - shadow_h), shadow)
            bottom_shadow = shadow.transpose(Image.FLIP_TOP_BOTTOM)
            canvas.paste(bottom_shadow, (0, offset_y + scaled_h), bottom_shadow)
            
        # Apply sharpening if upscaled
        if upscale in ["4k", "8k"]:
            try:
                canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
            except Exception:
                pass
                
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        canvas.save(output_path, quality=95)
        return 0, 0, W, H

    # 4. FIT MODE: BLUR PADDING (Center image over blurred copy)
    if fit == "blur":
        bg = img.resize((target_w, target_h), resampling)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=50))
        bg = ImageEnhance.Brightness(bg).enhance(0.5)
        
        orig_ratio = W / H
        target_canvas_ratio = target_w / target_h
        
        if orig_ratio > target_canvas_ratio:
            scaled_w = target_w
            scaled_h = int(target_w / orig_ratio)
        else:
            scaled_h = target_h
            scaled_w = int(target_h * orig_ratio)
            
        sharp_img = img.resize((scaled_w, scaled_h), resampling)
        
        if upscale in ["4k", "8k"]:
            try:
                sharp_img = sharp_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
            except Exception:
                pass
                
        offset_x = (target_w - scaled_w) // 2
        offset_y = (target_h - scaled_h) // 2
        bg.paste(sharp_img, (offset_x, offset_y))
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        bg.save(output_path, quality=95)
        return 0, 0, W, H

    # 5. FIT MODE: STRETCH TO FIT
    if fit == "stretch":
        stretched_img = img.resize((target_w, target_h), resampling)
        if upscale in ["4k", "8k"]:
            try:
                stretched_img = stretched_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
            except Exception:
                pass
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        stretched_img.save(output_path, quality=95)
        return 0, 0, W, H

    # 6. FIT MODE: SMART CROP (Edge Density scan)
    gray = img.convert('L')
    edges = gray.filter(ImageFilter.FIND_EDGES)
    
    max_dim = 200
    if W > H:
        w_small = max_dim
        h_small = max(10, int(max_dim * H / W))
    else:
        h_small = max_dim
        w_small = max(10, int(max_dim * W / H))
        
    edges_small = edges.resize((w_small, h_small))
    edge_data = np.array(edges_small)
    small_ratio = w_small / h_small
    
    if small_ratio > target_ratio:
        crop_h = h_small
        crop_w = int(h_small * target_ratio)
        crop_w = min(crop_w, w_small)
        
        best_score = -1
        best_x = 0
        limit = w_small - crop_w
        for x in range(limit + 1):
            window = edge_data[:, x:x+crop_w]
            edge_sum = np.sum(window)
            
            box_center = x + crop_w / 2
            img_center = w_small / 2
            dist_from_center = abs(box_center - img_center)
            max_dist = w_small / 2
            norm_dist = dist_from_center / max_dist if max_dist > 0 else 0
            
            score = edge_sum * (1.0 - center_bias * norm_dist)
            if score > best_score:
                best_score = score
                best_x = x
                
        scale = W / w_small
        final_x1 = int(best_x * scale)
        final_y1 = 0
        final_x2 = int((best_x + crop_w) * scale)
        final_y2 = H
        
    else:
        crop_w = w_small
        crop_h = int(w_small / target_ratio)
        crop_h = min(crop_h, h_small)
        
        best_score = -1
        best_y = 0
        limit = h_small - crop_h
        for y in range(limit + 1):
            window = edge_data[y:y+crop_h, :]
            edge_sum = np.sum(window)
            
            box_center = y + crop_h / 2
            img_center = h_small / 2
            dist_from_center = abs(box_center - img_center)
            max_dist = h_small / 2
            norm_dist = dist_from_center / max_dist if max_dist > 0 else 0
            
            score = edge_sum * (1.0 - center_bias * norm_dist)
            if score > best_score:
                best_score = score
                best_y = y
                
        scale = H / h_small
        final_x1 = 0
        final_y1 = int(best_y * scale)
        final_x2 = W
        final_y2 = int((best_y + crop_h) * scale)
        
    final_x1 = max(0, min(final_x1, W - 1))
    final_y1 = max(0, min(final_y1, H - 1))
    final_x2 = max(final_x1 + 1, min(final_x2, W))
    final_y2 = max(final_y1 + 1, min(final_y2, H))
    
    cropped_img = img.crop((final_x1, final_y1, final_x2, final_y2))
    
    if upscale in ["4k", "8k"]:
        cropped_img = cropped_img.resize((target_w, target_h), resampling)
        try:
            cropped_img = cropped_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
        except Exception:
            pass
            
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cropped_img.save(output_path, quality=95)
    return final_x1, final_y1, final_x2, final_y2
