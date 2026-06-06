from nicegui import ui, app
import os
import time
from pymongo import MongoClient
from Image_Automation.geminiImage import image_to_gemini
from playwright.sync_api import sync_playwright
import asyncio

# Database Setup
MONGO_URI = "mongodb://localhost:27017/"
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = client["image_generator_db"]
    history_col = db["history"]
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    history_col = None

# Directories
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
PLAYWRIGHT_PROFILE = r"C:\Users\Jay\AppData\Local\Google\Chrome\PlaywrightProfile"

# Global Light Mode Styling Override
ui.add_head_html('''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    body {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
</style>
''', shared=True)

# Authentication Middleware
from fastapi import Request
from starlette.responses import RedirectResponse

unrestricted_page_routes = {'/login'}

@app.middleware('http')
async def require_login(request: Request, call_next):
    if not app.storage.user.get('authenticated', False):
        if request.url.path not in unrestricted_page_routes and not request.url.path.startswith('/_nicegui'):
            return RedirectResponse('/login')
    return await call_next(request)


# --- Helper: Generate Image ---
def run_playwright_generator(image_path, prompt):
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_PROFILE,
                channel="chrome",
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                ignore_default_args=["--enable-automation"],
            )
            page = context.new_page()
            try:
                saved_path = image_to_gemini(page, image_path, prompt)
                return saved_path
            finally:
                context.close()
    except Exception as e:
        print(f"Error during image generation: {e}")
        return None

# --- UI Components ---
def navbar():
    ui.query('body').style('background-color: #f8fafc;')
    
    with ui.header().classes('items-center bg-white border-b border-slate-100 text-slate-800 px-6 py-4'):
        ui.button(icon='menu', on_click=lambda: left_drawer.toggle()).props('flat round dense').classes('text-slate-600')
        ui.label('Studio.ai').classes('text-xl font-bold tracking-tight text-slate-900 ml-2')
        ui.space()
        
        ui.button('Generate', on_click=lambda: ui.navigate.to('/')).props('flat text-color=slate-700').classes('capitalize font-medium text-sm mx-1')
        ui.button('History', on_click=lambda: ui.navigate.to('/history')).props('flat text-color=slate-700').classes('capitalize font-medium text-sm mx-1')
        
        with ui.button(icon='account_circle').props('flat round').classes('text-slate-600 ml-2'):
            with ui.menu().classes('border border-slate-100 shadow-xl rounded-xl'):
                ui.menu_item('Logout', on_click=lambda: (app.storage.user.clear(), ui.navigate.to('/login'))).classes('text-slate-700')

    with ui.left_drawer(value=False).classes('bg-white border-r border-slate-100 p-4') as left_drawer:
        ui.label('Navigation').classes('text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 px-3')
        ui.button('Dashboard', icon='dashboard', on_click=lambda: ui.navigate.to('/')).props('flat align=left').classes('w-full justify-start text-slate-700 rounded-lg py-2')
        ui.button('History Log', icon='history', on_click=lambda: ui.navigate.to('/history')).props('flat align=left').classes('w-full justify-start text-slate-700 rounded-lg py-2')

# --- Pages ---
@ui.page('/login')
def login_page():
    ui.query('body').style('background-color: #f8fafc;')
    
    with ui.card().classes('absolute-center w-full max-w-md p-8 rounded-2xl shadow-xl border border-slate-100 bg-white'):
        with ui.column().classes('w-full items-center mb-6'):
            ui.icon('auto_awesome', size='3rem').classes('text-blue-600 mb-2')
            ui.label('Welcome Back').classes('text-2xl font-bold text-slate-900 tracking-tight')
            ui.label('Sign in to your generator account').classes('text-sm text-slate-500')
        
        email = ui.input('Email Address').props('outlined dense').classes('w-full mb-4')
        password = ui.input('Password', password=True, password_toggle_button=True).props('outlined dense').classes('w-full mb-6')
        
        def try_login():
            if email.value == 'admin@example.com' and password.value == 'password':
                app.storage.user['authenticated'] = True
                ui.navigate.to('/')
            else:
                ui.notify('Invalid credentials', color='negative')
                
        ui.button('Sign In', on_click=try_login).props('unelevated color=primary').classes('w-full py-2.5 rounded-xl font-medium shadow-sm')


@ui.page('/')
def home_page():
    navbar()
    
    with ui.column().classes('w-full max-w-7xl mx-auto p-6 md:p-8 space-y-6'):
        with ui.column().classes('mb-2'):
            ui.label('AI Image Generator').classes('text-3xl font-bold tracking-tight text-slate-900')
            ui.label('Upload an existing photo to transform it using advanced vision models.').classes('text-slate-500 text-sm')
        
        with ui.grid(columns='1fr 1fr').classes('w-full gap-8 items-start md:grid-cols-2 grid-cols-1'):
            
            with ui.card().classes('w-full p-6 rounded-2xl shadow-sm border border-slate-100 bg-white space-y-6'):
                ui.label('Configuration Settings').classes('text-md font-bold text-slate-800 border-b border-slate-100 pb-3 w-full')
                
                with ui.column().classes('w-full space-y-1.5'):
                    ui.label('Prompt Logic').classes('text-xs font-semibold uppercase tracking-wider text-slate-400')
                    prompt_type = ui.radio(['Default', 'Custom'], value='Default').props('inline color=primary')
                
                prompt_input = ui.input('Transformation Prompt', value='give me a new t-shirt image from this').props('outlined dense').classes('w-full')
                
                def update_prompt(e):
                    if e.value == 'Default':
                        prompt_input.value = 'give me a new t-shirt image from this'
                    else:
                        prompt_input.value = ''
                prompt_type.on_value_change(update_prompt)
                
                with ui.row().classes('w-full gap-4'):
                    name = ui.input('Item Name (Optional)').props('outlined dense').classes('flex-1')
                    price = ui.input('Price (Optional)').props('outlined dense').classes('flex-1')
                
                with ui.column().classes('w-full space-y-1.5'):
                    ui.label('Source Media Asset').classes('text-xs font-semibold uppercase tracking-wider text-slate-400')
                    
                    # Store the path in a mutable state object for this page
                    uploaded_file_path = {"path": ""}
                    
                    async def handle_upload(e):
                        file_bytes = await e.file.read()
                        path = os.path.join(UPLOADS_DIR, e.file.name)
                        with open(path, 'wb') as f:
                            f.write(file_bytes)
                        
                        # Store in our state dict
                        uploaded_file_path["path"] = path
                        ui.notify(f'Uploaded {e.file.name} successfully!', color='positive')
                        
                    ui.upload(on_upload=handle_upload, multiple=False, auto_upload=True, label="Drop your file here").classes('w-full border-2 border-dashed border-slate-200 rounded-xl bg-slate-50 shadow-none').props('accept="image/*" flat')
                
                submit_btn = ui.button('Generate Asset', color='primary', icon='bolt').props('unelevated').classes('w-full py-3 rounded-xl font-semibold shadow-sm text-sm capitalize tracking-wide')
                
                with ui.row().classes('w-full justify-center items-center h-8') as spinner_container:
                    ui.spinner('indigo', size='md').classes('mr-2')
                    ui.label('Processing background worker engines...').classes('text-xs font-medium text-slate-500')
                spinner_container.set_visibility(False)
                
                async def submit():
                    # Read from state dict
                    current_upload_path = uploaded_file_path["path"]
                    
                    if not current_upload_path or current_upload_path == '':
                        ui.notify('Please upload a source image first.', color='warning')
                        return
                    
                    spinner_container.set_visibility(True)
                    submit_btn.disable()
                    
                    loop = asyncio.get_running_loop()
                    result_path = await loop.run_in_executor(None, run_playwright_generator, current_upload_path, prompt_input.value)
                    
                    spinner_container.set_visibility(False)
                    submit_btn.enable()
                    
                    if result_path and os.path.exists(result_path):
                        gemini_dir = os.path.dirname(result_path)
                        app.add_static_files('/gemini_images', gemini_dir)
                        
                        filename = os.path.basename(result_path)
                        result_image.set_source(f'/gemini_images/{filename}')
                        
                        if history_col is not None:
                            record = {
                                "prompt": prompt_input.value,
                                "name": name.value,
                                "price": price.value,
                                "original_image": current_upload_path,
                                "generated_image": filename,
                                "timestamp": time.time()
                            }
                            history_col.insert_one(record)
                        ui.notify('Image generated successfully!', color='positive')
                        uploaded_file_path["path"] = ''  # Clear tracking
                    else:
                        ui.notify('Failed to generate image', color='negative')
                
                submit_btn.on_click(submit)
            
            with ui.card().classes('w-full p-6 rounded-2xl shadow-sm border border-slate-100 bg-white space-y-4'):
                ui.label('Live Output Canvas').classes('text-md font-bold text-slate-800 border-b border-slate-100 pb-3 w-full')
                result_image = ui.image().classes('w-full rounded-xl bg-slate-50 object-cover border border-slate-100').style('min-height: 420px; max-height: 500px;')
                result_image.set_source('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=800&auto=format&fit=crop')


@ui.page('/history')
def history_page():
    navbar()
    
    with ui.column().classes('w-full max-w-7xl mx-auto p-6 md:p-8 space-y-6'):
        with ui.column():
            ui.label('Generation History Portfolio').classes('text-3xl font-bold tracking-tight text-slate-900')
            ui.label('Browse your historically generated structural templates and models.').classes('text-slate-500 text-sm')
        
        if history_col is None:
            with ui.card().classes('w-full p-6 bg-red-50 border border-red-100 rounded-xl items-center text-center'):
                ui.icon('error_outline', color='red', size='2.5rem')
                ui.label('MongoDB connection is unavailable. Verify connection configs.').classes('text-red-700 font-medium mt-2')
            return
            
        records = list(history_col.find().sort("timestamp", -1))
        
        if not records:
            with ui.card().classes('w-full p-12 bg-white border border-slate-100 rounded-2xl items-center text-center shadow-sm'):
                ui.icon('cloud_off', color='slate-300', size='4rem').classes('mb-2')
                ui.label('No generations cataloged.').classes('text-lg font-semibold text-slate-700')
                ui.label('Head over back to the generator module to create a new record.').classes('text-slate-400 text-sm max-w-sm mt-1')
            return
            
        gemini_dir = os.path.join(os.path.dirname(__file__), "Image_Automation", "gemini")
        os.makedirs(gemini_dir, exist_ok=True)
        app.add_static_files('/gemini_images', gemini_dir)
            
        with ui.grid(columns='1fr 1fr 1fr').classes('w-full gap-6 md:grid-cols-3 sm:grid-cols-2 grid-cols-1'):
            for record in records:
                with ui.card().classes('w-full overflow-hidden p-0 rounded-2xl border border-slate-100 shadow-sm bg-white group hover:shadow-md transition-shadow duration-200'):
                    filename = record.get("generated_image")
                    if filename:
                        ui.image(f'/gemini_images/{filename}').classes('w-full h-56 object-cover bg-slate-50 border-b border-slate-100')
                    
                    with ui.column().classes('p-5 w-full space-y-2'):
                        ui.label(record.get('prompt', 'N/A')).classes('font-semibold text-slate-800 text-sm line-clamp-2 leading-snug')
                        
                        if record.get('name') or record.get('price'):
                            with ui.row().classes('w-full gap-2 pt-1 items-center'):
                                if record.get('name'):
                                    ui.badge(record.get('name'), color='blue-100').classes('text-blue-700 text-xs px-2.5 py-1 rounded-md shadow-none font-medium')
                                if record.get('price'):
                                    ui.badge(f"${record.get('price')}", color='emerald-100').classes('text-emerald-700 text-xs px-2.5 py-1 rounded-md shadow-none font-medium')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Image Generator", port=8080, storage_secret="super-secret-key")