from flask import Flask, request, render_template, send_from_directory, jsonify
import os
from werkzeug.utils import secure_filename
import json
import pathlib
import tempfile
import shutil
from filelock import FileLock
import time
import uuid

# Configure upload folder and chunk folder with proper path handling
BASE_DIR = pathlib.Path(__file__).parent.absolute()
UPLOAD_FOLDER = BASE_DIR / 'uploads'
CHUNK_FOLDER = BASE_DIR / 'chunks'
LOCK_FOLDER = BASE_DIR / 'locks'
TEMP_FOLDER = BASE_DIR / 'temp'
TEMPLATE_FOLDER = BASE_DIR / 'templates'

# Create directories if they don't exist
UPLOAD_FOLDER.mkdir(exist_ok=True)
CHUNK_FOLDER.mkdir(exist_ok=True)
LOCK_FOLDER.mkdir(exist_ok=True)
TEMP_FOLDER.mkdir(exist_ok=True)
TEMPLATE_FOLDER.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(TEMPLATE_FOLDER))
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['CHUNK_FOLDER'] = str(CHUNK_FOLDER)
app.config['LOCK_FOLDER'] = str(LOCK_FOLDER)
app.config['TEMP_FOLDER'] = str(TEMP_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50GB max file size

def get_file_sizes():
    """Get sizes of all files in the upload folder"""
    sizes = {}
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(file_path):
            sizes[filename] = os.path.getsize(file_path)
    return sizes

def get_lock_path(identifier, chunk_number):
    """Get the lock file path for a specific chunk"""
    return pathlib.Path(app.config['LOCK_FOLDER']) / f"{identifier}_{chunk_number}.lock"

def cleanup_stale_files():
    """Clean up stale temporary files and locks older than 1 hour"""
    current_time = time.time()
    # Clean up locks
    for lock_file in pathlib.Path(app.config['LOCK_FOLDER']).glob('*.lock'):
        if current_time - lock_file.stat().st_mtime > 3600:  # 1 hour
            try:
                lock_file.unlink()
            except:
                pass
    
    # Clean up temp files
    for temp_file in pathlib.Path(app.config['TEMP_FOLDER']).glob('*'):
        if current_time - temp_file.stat().st_mtime > 3600:  # 1 hour
            try:
                temp_file.unlink()
            except:
                pass

@app.route('/')
def index():
    cleanup_stale_files()
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    file_sizes = get_file_sizes()
    return render_template('index.html', files=files, file_sizes=file_sizes)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'GET':
        # Handle chunk test request
        chunk_number = request.args.get('resumableChunkNumber', type=int)
        identifier = request.args.get('resumableIdentifier', type=str)
        
        if all([chunk_number, identifier]):
            chunk_file = pathlib.Path(app.config['CHUNK_FOLDER']) / f"{identifier}_{chunk_number}"
            if chunk_file.exists():
                return jsonify({"found": True}), 200
        return jsonify({"found": False}), 404

    if request.method == 'POST':
        try:
            chunk_number = request.form.get('resumableChunkNumber', type=int)
            total_chunks = request.form.get('resumableTotalChunks', type=int)
            identifier = request.form.get('resumableIdentifier', type=str)
            filename = secure_filename(request.form.get('resumableFilename', ''))

            if not all([chunk_number, total_chunks, identifier, filename]):
                return jsonify({"error": "Missing parameters"}), 400

            # Create a lock file for this chunk
            lock_path = get_lock_path(identifier, chunk_number)
            lock = FileLock(str(lock_path), timeout=60)  # 60 second timeout

            try:
                with lock:
                    # Save chunk directly to chunk folder
                    chunk_file = pathlib.Path(app.config['CHUNK_FOLDER']) / f"{identifier}_{chunk_number}"
                    chunk_file.parent.mkdir(exist_ok=True)
                    
                    # Write chunk data directly
                    request.files['file'].save(str(chunk_file))

                # Check if all chunks are uploaded
                uploaded_chunks = list(pathlib.Path(app.config['CHUNK_FOLDER']).glob(f"{identifier}_*"))
                
                if len(uploaded_chunks) == total_chunks:
                    # Sort chunks to ensure correct order
                    uploaded_chunks.sort(key=lambda x: int(str(x).split('_')[-1]))
                    
                    # Combine all chunks with a lock
                    combine_lock_path = get_lock_path(identifier, "combine")
                    combine_lock = FileLock(str(combine_lock_path), timeout=300)  # 5 minute timeout for combining
                    
                    try:
                        with combine_lock:
                            final_filepath = pathlib.Path(app.config['UPLOAD_FOLDER']) / filename
                            
                            # Combine chunks directly into final file
                            with open(final_filepath, 'wb') as final_file:
                                for chunk in uploaded_chunks:
                                    with open(chunk, 'rb') as chunk_file:
                                        shutil.copyfileobj(chunk_file, final_file)
                                    try:
                                        chunk.unlink()  # Remove chunk after combining
                                    except:
                                        pass  # Ignore errors during cleanup
                            
                            # Clean up locks
                            for i in range(total_chunks):
                                try:
                                    lock_file = get_lock_path(identifier, i+1)
                                    lock_file.unlink()
                                except:
                                    pass
                    finally:
                        try:
                            combine_lock_path.unlink()  # Remove the combine lock
                        except:
                            pass
                    
                    return jsonify({"status": "File uploaded successfully"}), 200
                
                return jsonify({"status": "Chunk uploaded successfully"}), 200

            except Exception as e:
                app.logger.error(f"Chunk upload error: {str(e)}")
                return jsonify({"error": str(e)}), 500
            finally:
                try:
                    lock_path.unlink()  # Clean up the lock file
                except:
                    pass

        except Exception as e:
            app.logger.error(f"Upload error: {str(e)}")
            return jsonify({"error": str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True) 