import os
import uuid
import json
import logging
import asyncio
import time
import shutil
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageFilter
from scraper import search_pinterest_images, download_image

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PinCrop-API")

app = FastAPI(title="PinCrop API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Media directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

# User's local Pictures directory for PinCrop
USER_PICTURES_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "PinCrop")
os.makedirs(USER_PICTURES_DIR, exist_ok=True)

# Mount static files to serve the generated images
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

HISTORY_FILE = os.path.join(MEDIA_DIR, "history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_history(item):
    history = load_history()
    # Check if item already exists by ID
    existing_idx = -1
    for idx, hist_item in enumerate(history):
        if hist_item.get("id") == item["id"]:
            existing_idx = idx
            break
            
    if existing_idx != -1:
        # Update existing session, and move it to the top
        history.pop(existing_idx)
        history.insert(0, item)
    else:
        # Insert at the beginning so newest is first
        history.insert(0, item)
        
    # Keep last 50 items
    history = history[:50]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

class GenerateRequest(BaseModel):
    query: str
    limit: int = 10
    session_id: Optional[str] = None
    upscale: str = "none" # "none", "4k", "8k"

class RotateRequest(BaseModel):
    session_id: str
    index: int
    direction: str # "cw" or "ccw"
    upscale: str = "none"

class RegenerateRequest(BaseModel):
    session_id: str
    index: int
    upscale: str = "none"

def render_wallpaper_file(orig_path, render_path, upscale, source_type):
    """
    Renders the wallpaper. If upscale is requested, resizes proportionally and sharpens.
    Otherwise, copies the file directly.
    """
    try:
        if upscale not in ["4k", "8k"]:
            shutil.copy2(orig_path, render_path)
            return
            
        img = Image.open(orig_path)
        W, H = img.size
        
        # Calculate target width based on upscale and orientation
        if source_type == "desktop":
            target_w = 3840 if upscale == "4k" else 7680
        else: # mobile
            target_w = 2160 if upscale == "4k" else 4320
            
        target_h = int(target_w * H / W)
        
        try:
            resampling = Image.Resampling.LANCZOS
        except AttributeError:
            resampling = Image.LANCZOS
            
        logger.info(f"Upscaling wallpaper to {target_w}x{target_h} ({upscale.upper()})...")
        img_resized = img.resize((target_w, target_h), resampling)
        
        # Apply high-fidelity sharpening filter
        img_sharpened = img_resized.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
        img_sharpened.save(render_path, quality=95)
    except Exception as e:
        logger.error(f"Failed to render/upscale wallpaper: {e}")
        shutil.copy2(orig_path, render_path)

@app.post("/api/generate")
async def generate_wallpapers(request: GenerateRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=404, detail="Query cannot be empty")
        
    limit = request.limit
    session_id = request.session_id
    upscale = request.upscale.lower()
    
    if upscale not in ["none", "4k", "8k"]:
        upscale = "none"
        
    # Generate unique ID or load existing session
    if session_id:
        unique_id = session_id
        # Find existing session in history
        history = load_history()
        existing_session = None
        for item in history:
            if item.get("id") == unique_id:
                existing_session = item
                break
                
        if not existing_session:
            raise HTTPException(status_code=404, detail="Session not found in history")
            
        query = existing_session.get("query", query)
        generated_wallpapers = existing_session.get("wallpapers", [])
        existing_urls = {wp["original_url"] for wp in generated_wallpapers}
        user_query_dir = existing_session.get("local_folder")
        sanitized_query = "".join(c if c.isalnum() else "_" for c in query.lower())[:30]
        
        # Verify user_query_dir exists
        if not user_query_dir or not os.path.exists(user_query_dir):
            user_query_dir = os.path.join(USER_PICTURES_DIR, f"{sanitized_query}_{unique_id}")
            os.makedirs(user_query_dir, exist_ok=True)
            
        logger.info(f"Generating MORE wallpapers for session {unique_id} (limit: {limit}, upscale: {upscale.upper()}). Existing count: {len(generated_wallpapers)}")
    else:
        unique_id = str(uuid.uuid4())[:8]
        sanitized_query = "".join(c if c.isalnum() else "_" for c in query.lower())[:30]
        user_query_dir = os.path.join(USER_PICTURES_DIR, f"{sanitized_query}_{unique_id}")
        os.makedirs(user_query_dir, exist_ok=True)
        generated_wallpapers = []
        existing_urls = set()
        logger.info(f"Received request for {limit} new wallpapers: {query} (upscale: {upscale.upper()})")
        
    # Split limit 50/50 between Desktop-oriented search and Mobile-oriented search
    desktop_limit = limit // 2
    mobile_limit = limit - desktop_limit
    
    if limit == 1:
        desktop_limit = 1
        mobile_limit = 0
        
    try:
        # 1. Search Pinterest for both widescreen and portrait images sequentially
        async def search_with_fallback(search_q, req_limit):
            from scraper import search_pinterest_images
            results = await search_pinterest_images(search_q, req_limit)
            if not results:
                logger.warning(f"No results for query '{search_q}'. Falling back to generic query '{query}'.")
                results = await search_pinterest_images(query, req_limit)
            return results or []

        logger.info(f"Searching Pinterest sequentially: Desktop limit={desktop_limit}, Mobile limit={mobile_limit}")
        
        desktop_raw_results = await search_with_fallback(f"{query} desktop wallpaper 1920x1080", max(1, desktop_limit * 2))
        mobile_raw_results = await search_with_fallback(f"{query} phone wallpaper 1080x1920", max(1, mobile_limit * 2))
        
        starting_index = len(generated_wallpapers) + 1
        
        # Helper function to process a single image concurrently
        async def process_single_image(wp_num, url, title, source_type):
            img_id = f"{unique_id}_{wp_num}"
            orig_filename = f"original_{sanitized_query}_{img_id}.jpg"
            render_filename = f"rendered_{sanitized_query}_{img_id}.jpg"
            
            orig_path = os.path.join(MEDIA_DIR, orig_filename)
            render_path = os.path.join(MEDIA_DIR, render_filename)
            
            try:
                # Download
                logger.info(f"Downloading new image {wp_num} from {url}...")
                download_success = await asyncio.to_thread(download_image, url, orig_path)
                if not download_success:
                    logger.warning(f"Failed to download image {wp_num}. Skipping.")
                    return None
            except Exception as download_err:
                logger.warning(f"Network error downloading image {wp_num} from {url}: {download_err}")
                return None
                
            try:
                # Render/Upscale the image to target path
                await asyncio.to_thread(render_wallpaper_file, orig_path, render_path, upscale, source_type)
                
                # Copy original and rendered images to user's local Pictures directory
                user_orig_path = os.path.join(user_query_dir, orig_filename)
                user_render_path = os.path.join(user_query_dir, render_filename)
                shutil.copy2(orig_path, user_orig_path)
                shutil.copy2(render_path, user_render_path)
                
                return {
                    "index": wp_num,
                    "title": title,
                    "original_url": url,
                    "original_local": f"/media/{orig_filename}",
                    "desktop_url": f"/media/{render_filename}" if source_type == "desktop" else None,
                    "mobile_url": f"/media/{render_filename}" if source_type == "mobile" else None,
                    "original_pc_path": user_orig_path,
                    "desktop_pc_path": user_render_path if source_type == "desktop" else None,
                    "mobile_pc_path": user_render_path if source_type == "mobile" else None,
                    "source_type": source_type,
                    "upscale": upscale
                }
            except Exception as e:
                logger.error(f"Error copying/saving image {wp_num}: {e}")
                for p in [orig_path, render_path]:
                    if os.path.exists(p):
                        try: os.remove(p)
                        except: pass
                return None

        # 2. Build concurrent tasks list, launching extra tasks to cover potential download failures
        desk_tasks = []
        desk_added_urls = set()
        desk_wp_num = starting_index
        
        for res in desktop_raw_results:
            url = res["url"]
            if url in existing_urls or url in desk_added_urls:
                continue
            desk_tasks.append(process_single_image(desk_wp_num, url, res["title"], "desktop"))
            desk_added_urls.add(url)
            desk_wp_num += 1
            if len(desk_tasks) >= desktop_limit + 3:  # Allow up to 3 failures
                break
                
        mob_tasks = []
        mob_added_urls = set()
        mob_wp_num = starting_index + len(desk_tasks)
        
        for res in mobile_raw_results:
            url = res["url"]
            if url in existing_urls or url in mob_added_urls or url in desk_added_urls:
                continue
            mob_tasks.append(process_single_image(mob_wp_num, url, res["title"], "mobile"))
            mob_added_urls.add(url)
            mob_wp_num += 1
            if len(mob_tasks) >= mobile_limit + 3:  # Allow up to 3 failures
                break
                
        if not desk_tasks and not mob_tasks:
            raise Exception("No new unique wallpapers found to generate.")
            
        # 3. Execute all download tasks concurrently
        logger.info(f"Executing {len(desk_tasks)} desktop tasks and {len(mob_tasks)} mobile tasks concurrently...")
        
        desk_results, mob_results = await asyncio.gather(
            asyncio.gather(*desk_tasks),
            asyncio.gather(*mob_tasks)
        )
        
        # Filter successful results and slice to exact requested limits
        valid_desktops = [wp for wp in desk_results if wp is not None][:desktop_limit]
        valid_mobiles = [wp for wp in mob_results if wp is not None][:mobile_limit]
        
        combined_new = valid_desktops + valid_mobiles
        
        if not combined_new:
            raise Exception("Failed to download any new unique images.")
            
        # Re-index sequentially to fix any gaps
        for idx, wp in enumerate(combined_new):
            wp["index"] = starting_index + idx
            generated_wallpapers.append(wp)
            
        # Create response item
        result_item = {
            "id": unique_id,
            "query": query,
            "wallpapers": generated_wallpapers,
            "local_folder": user_query_dir,
            "timestamp": time.time()
        }
        
        # Save to history
        save_to_history(result_item)
        
        return result_item
        
    except Exception as e:
        logger.error(f"Error generating wallpapers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rotate")
async def rotate_wallpaper(request: RotateRequest):
    session_id = request.session_id
    index = request.index
    direction = request.direction.lower()
    upscale = request.upscale.lower()
    
    if upscale not in ["none", "4k", "8k"]:
        upscale = "none"
        
    # 1. Load history
    history = load_history()
    existing_session = None
    session_idx = -1
    for idx, item in enumerate(history):
        if item.get("id") == session_id:
            existing_session = item
            session_idx = idx
            break
            
    if not existing_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    wallpapers = existing_session.get("wallpapers", [])
    target_wp = None
    wp_idx = -1
    for idx, wp in enumerate(wallpapers):
        if wp.get("index") == index:
            target_wp = wp
            wp_idx = idx
            break
            
    if not target_wp:
        raise HTTPException(status_code=404, detail="Wallpaper not found in session")
        
    orig_local_path = os.path.join(BASE_DIR, target_wp["original_local"].lstrip("/"))
    orig_pc_path = target_wp["original_pc_path"]
    
    try:
        # 2. Rotate original image on disk
        angle = 270 if direction == "cw" else 90
        logger.info(f"Rotating original image for index {index} by {angle} degrees...")
        
        img = Image.open(orig_local_path)
        rotated_img = img.rotate(angle, expand=True)
        
        # Overwrite original images
        rotated_img.save(orig_local_path, quality=95)
        if os.path.exists(orig_pc_path):
            rotated_img.save(orig_pc_path, quality=95)
            
        # Flip source type if rotated by 90 degrees
        current_type = target_wp.get("source_type", "desktop")
        new_type = "mobile" if current_type == "desktop" else "desktop"
        target_wp["source_type"] = new_type
        
        # 3. Re-render the upscaled version from the rotated original
        render_local_path = os.path.join(BASE_DIR, (target_wp["desktop_url"] or target_wp["mobile_url"]).lstrip("/"))
        render_pc_path = target_wp["desktop_pc_path"] or target_wp["mobile_pc_path"]
        
        logger.info(f"Re-rendering rotated image to render path: {render_local_path}")
        await asyncio.to_thread(render_wallpaper_file, orig_local_path, render_local_path, upscale, new_type)
        if os.path.exists(render_pc_path):
            shutil.copy2(render_local_path, render_pc_path)
            
        # Also flip the desktop_url and mobile_url values in metadata
        if new_type == "desktop":
            target_wp["desktop_url"] = target_wp["desktop_url"] or target_wp["mobile_url"]
            target_wp["desktop_pc_path"] = target_wp["desktop_pc_path"] or target_wp["mobile_pc_path"]
            target_wp["mobile_url"] = None
            target_wp["mobile_pc_path"] = None
        else:
            target_wp["mobile_url"] = target_wp["mobile_url"] or target_wp["desktop_url"]
            target_wp["mobile_pc_path"] = target_wp["mobile_pc_path"] or target_wp["desktop_pc_path"]
            target_wp["desktop_url"] = None
            target_wp["desktop_pc_path"] = None
            
        target_wp["upscale"] = upscale
        # Save updated history
        existing_session["wallpapers"][wp_idx] = target_wp
        history[session_idx] = existing_session
        
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
            
        return existing_session
        
    except Exception as e:
        logger.error(f"Error rotating image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/regenerate")
async def regenerate_wallpaper(request: RegenerateRequest):
    session_id = request.session_id
    index = request.index
    upscale = request.upscale.lower()
    
    if upscale not in ["none", "4k", "8k"]:
        upscale = "none"
        
    # 1. Load history
    history = load_history()
    existing_session = None
    session_idx = -1
    for idx, item in enumerate(history):
        if item.get("id") == session_id:
            existing_session = item
            session_idx = idx
            break
            
    if not existing_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    wallpapers = existing_session.get("wallpapers", [])
    target_wp = None
    wp_idx = -1
    for idx, wp in enumerate(wallpapers):
        if wp.get("index") == index:
            target_wp = wp
            wp_idx = idx
            break
            
    if not target_wp:
        raise HTTPException(status_code=404, detail="Wallpaper not found in session")
        
    orig_local_path = os.path.join(BASE_DIR, target_wp["original_local"].lstrip("/"))
    
    # Extract source type and paths
    source_type = target_wp["source_type"]
    render_filename = f"rendered_{session_id}_{index}.jpg" # fallback name if missing
    
    if source_type == "desktop":
        if not target_wp.get("desktop_url"):
            target_wp["desktop_url"] = f"/media/{render_filename}"
        render_local_path = os.path.join(BASE_DIR, target_wp["desktop_url"].lstrip("/"))
        render_pc_path = target_wp["desktop_pc_path"]
        if not render_pc_path:
            render_pc_path = os.path.join(existing_session["local_folder"], render_filename)
            target_wp["desktop_pc_path"] = render_pc_path
    else:
        if not target_wp.get("mobile_url"):
            target_wp["mobile_url"] = f"/media/{render_filename}"
        render_local_path = os.path.join(BASE_DIR, target_wp["mobile_url"].lstrip("/"))
        render_pc_path = target_wp["mobile_pc_path"]
        if not render_pc_path:
            render_pc_path = os.path.join(existing_session["local_folder"], render_filename)
            target_wp["mobile_pc_path"] = render_pc_path
            
    try:
        # Re-render / Re-upscale
        logger.info(f"Re-rendering/upscaling wallpaper index {index} to resolution {upscale.upper()}...")
        await asyncio.to_thread(render_wallpaper_file, orig_local_path, render_local_path, upscale, source_type)
        shutil.copy2(render_local_path, render_pc_path)
        
        # Save updated history
        target_wp["upscale"] = upscale
        existing_session["wallpapers"][wp_idx] = target_wp
        history[session_idx] = existing_session
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
            
        return existing_session
    except Exception as e:
        logger.error(f"Error regenerating wallpaper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    return load_history()

if __name__ == "__main__":
    import uvicorn
    import sys
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
