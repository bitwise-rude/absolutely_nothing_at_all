import os
import time
import queue
import threading
import requests
from flask import Flask, render_template, jsonify, request, url_for, redirect, send_from_directory
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import re
import numpy as np
from werkzeug.utils import secure_filename
from groq import Groq
import json
import re
import time


app = Flask(__name__)
os.makedirs('static/images', exist_ok=True)
os.makedirs('templates', exist_ok=True)
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
working_batches = ['080','081','079','078']
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
image_queue = queue.Queue()
successful_images = {}
processing_status = {"active": True, "total": 0, "completed": 0}
file_loaded = open("080.txt", 'r')
all_data = file_loaded.read()
file_loaded.close()
all_students = {}
def load_existing_images():
    print("Scanning for existing images...")
    count = 0
    image_files = os.listdir('static/images')
    for filename in image_files:
        if filename.endswith('.png') or filename.endswith('.jpg'):
            roll_no = os.path.splitext(filename)[0]
            if roll_no[0:3] in working_batches:
                successful_images[roll_no] = f"static/images/{filename}"
                count += 1
    print(f"Loaded {count} existing images")
    return count
from groq import Groq
import json
import re
import time

def parse_student_data():
    # Initialize Groq client (put your API key here)
    client = Groq(api_key="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")
    
    all_students = {}
    pattern = r'PUL\d{3}(BCE|BEL|BCT|BEI|BME|BCH|BAS|BAR)\d{3}'
    lines = all_data.splitlines()
    
    for line in lines:
        for match in re.finditer(pattern, line):
            try:
                roll_no = match.group(0)
                roll_index = line.find(roll_no)
                section = line[roll_index:].strip()
                
                # Create prompt for Groq
                messages = [
                    {
                        "role": "system",
                        "content": "You are a data extraction expert. Extract student information and return ONLY valid JSON. Be precise and don't guess missing information."
                    },
                    {
                        "role": "user", 
                        "content": f"""Extract student data from this text and return ONLY valid JSON:

{section}

Return JSON with these exact fields (use null for missing data):
{{
  "Name": "",
  "Gender": "",
  "FatherName": "",
  "MotherName": "",
  "DOB": "",
  "Phone": "",
  "Department": "",
  "ProgramType": "",
  "RollNo": "{roll_no}",
  "Country": "",
  "District": "",
  "Municipality": "",
  "Grade10School": "",
  "Grade10Year": "",
  "Grade10GPA": "",
  "Grade12School": "",
  "Grade12Year": "",
  "Grade12ExamYear": "",
  "Grade12GPA": "",
  "Grade12Roll": ""
}}"""
                    }
                ]
                
                # Get response from Groq (super fast!)
                chat_completion = client.chat.completions.create(
                    messages=messages,
                    model="llama3-8b-8192",  # Current available model
                    temperature=0,
                    max_tokens=1000
                )
                
                response_text = chat_completion.choices[0].message.content.strip()
                
                # Debug: print raw response for first few students
                if len(all_students) < 3:
                    print(f"Raw response for {roll_no}: {response_text}")
                
                # Clean response (remove markdown if present)
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                elif response_text.startswith('```'):
                    response_text = response_text[3:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                
                # Remove any extra text before/after JSON
                response_text = response_text.strip()
                
                # Find JSON object in response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_text = response_text[start_idx:end_idx]
                else:
                    print(f"No JSON found in response for {roll_no}")
                    continue
                
                # Parse JSON and store
                student_data = json.loads(json_text)
                all_students[roll_no] = student_data
                
                print(f"Parsed {roll_no} successfully")
                
                # Very small delay (Groq is fast and has generous limits)
                time.sleep(0.05)
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error for {roll_no}: {e}")
                print(f"Cleaned response: {json_text if 'json_text' in locals() else response_text}")
                continue
            except Exception as e:
                print(f"Error parsing data for {roll_no}: {e}")
                continue
    
    print(f"Parsed {len(all_students)} student records")
    return all_students
all_students=parse_student_data()
def get_student_info(roll_no):
    return all_students.get(roll_no, {})
def generate_roll_numbers():
    departments = ["BEL","BCT","BCE","BCH","BAS","BEI","BME","BAR"]
    batches = working_batches
    roll_numbers = []
    for batch in batches:
        for dept in departments:
            if dept == "BCE":
                for num in range(1, 193):  
                    roll_no = f"{batch}{dept}{num:03d}"
                    roll_numbers.append(roll_no)
            else:
                for num in range(1, 97):  # 001 to 192
                    roll_no = f"{batch}{dept}{num:03d}"
                    roll_numbers.append(roll_no)
    print(roll_numbers)
    return roll_numbers
def startup_tasks():
    image_count = load_existing_images()
    processing_status["completed"] = image_count
    print(f"Application initialized with {image_count} cached images")
startup_tasks()

@app.route('/search-by-face', methods=['POST'])
def search_by_face():
    return jsonify({'status': 'error', 'message': 'Invalid file type'})

def fetch_profile_image(roll_no):
    img_path = (f"static/images/{roll_no}.png" if "080" in roll_no else f"static/images/{roll_no}.jpg")
    if os.path.exists(img_path):
        successful_images[roll_no] = img_path
        return img_path
    
    base_url = 'http://pulchowk.elibrary.edu.np/'
    login_url = f'{base_url}Account/Login'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    session = requests.Session()
    login_payload = {
        'username': roll_no,
        'password': roll_no
    }
    
    try:
        login_response = session.post(login_url, data=login_payload, headers=headers, timeout=5)
        if login_response.status_code != 200:
            # Create blank image if login fails
            return create_blank_image(roll_no, img_path)
            
        profile_page_url = base_url
        profile_response = session.get(profile_page_url, timeout=5)
        profile_response.raise_for_status()
        
        soup = BeautifulSoup(profile_response.text, 'html.parser')
        img_tag = soup.find('img', id='profilePhoto')
        
        if img_tag and 'src' in img_tag.attrs:
            profile_img_url = img_tag['src']
            img_response = session.get(profile_img_url + (".png" if "080" in roll_no else ".jpg"), timeout=5)
            img_response.raise_for_status()
            
            img_data = img_response.content
            img = Image.open(BytesIO(img_data))
            img = img.resize((150, 150)) 
            img.save(img_path)
            return img_path
        else:
            # Create blank image if profile photo not found
            return create_blank_image(roll_no, img_path)
            
    except Exception as e:
        print(f"Error fetching image for {roll_no}: {e}")
        # Create blank image on any error
        return create_blank_image(roll_no, img_path)

def create_blank_image(roll_no, img_path):
    """Create a blank image with roll number text in the center"""
    try:
        # Create a blank image with light gray background
        img = Image.new('RGB', (150, 150), color=(240, 240, 240))
        
        # Get a drawing context
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        
        # Try to use a default font
        try:
            # Try to load a system font - adjust path if needed for your OS
            font = ImageFont.truetype("arial.ttf", 16)
        except IOError:
            # If the specific font isn't available, use default
            font = ImageFont.load_default()
        
        # Draw the roll number text
        student_info = all_students.get(f"PUL{roll_no}", {})
        text = student_info.get('Name', roll_no) # Use name if available, otherwise use roll number
        text_width, text_height = draw.textbbox((0, 0), text, font=font)[2:4]
        position = ((150 - text_width) // 2, (150 - text_height) // 2)
        draw.text(position, text, fill=(100, 100, 100), font=font)
    
        
        # Save the image
        img.save(img_path)
        successful_images[roll_no] = img_path
        return img_path
        
    except Exception as e:
        print(f"Error creating blank image for {roll_no}: {e}")
        return None

def image_worker():
    while processing_status["active"]:
        try:
            roll_no = image_queue.get(timeout=1)
            img_path = fetch_profile_image(roll_no)
            processing_status["completed"] += 1
            if img_path:
                successful_images[roll_no] = img_path
            image_queue.task_done()
        except queue.Empty:
            time.sleep(0.5)
        except Exception as e:
            print(f"Error in worker: {e}")
            processing_status["completed"] += 1
            image_queue.task_done()
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/start-processing')
def start_processing():
    processing_status["total"] = 0
    processing_status["completed"] = 0
    processing_status["active"] = True
    roll_numbers = generate_roll_numbers()
    existing_count = len(successful_images)
    to_process = []
    for roll_no in roll_numbers:
        img_path = (f"static/images/{roll_no}.png" if "080" in roll_no else f"static/images/{roll_no}.jpg")
        if not os.path.exists(img_path):
            to_process.append(roll_no)
    processing_status["total"] = len(roll_numbers)
    processing_status["completed"] = processing_status["total"] - len(to_process)
    print(f"Starting processing: {len(to_process)} images to download, {processing_status['completed']} already cached")
    for roll_no in to_process:
        image_queue.put(roll_no)
    if to_process:
        num_workers = min(10, os.cpu_count() or 2)
        for _ in range(num_workers):
            worker_thread = threading.Thread(target=image_worker)
            worker_thread.daemon = True
            worker_thread.start()
    return redirect(url_for('index'))
@app.route('/search-students')
def search_students():
    search_term = request.args.get('term', '')
    if not search_term:
        return jsonify({
            'status': 'error',
            'message': 'No search term provided'
        })
    
    search_term = search_term.upper()
    results = []
    
    # Handle roll number search
    if search_term.startswith('PUL') or search_term.isdigit():
        roll_no = search_term
        if not search_term.startswith('PUL') and search_term.isdigit():
            roll_no = f"PUL{search_term}"   
        student = get_student_info(roll_no)
        if student:
            roll_no_without_prefix = roll_no.replace('PUL', '')
            img_path = f"static/images/{roll_no_without_prefix}.png" if "080" in roll_no else f"static/images/{roll_no_without_prefix}.jpg"
            if os.path.exists(img_path):
                image_url = img_path
            else:
                image_url = None
            results.append({
                'rollNo': roll_no,
                'name': student.get('Name'),
                'department': student.get('Department'),
                'imagePath': image_url
            })
    # Handle name search - improved to use partial matching
    else:
        for roll_no, student in all_students.items():
            if student.get('Name') and search_term in student.get('Name', '').upper():
                roll_no_without_prefix = roll_no.replace('PUL', '')
                img_path = f"static/images/{roll_no_without_prefix}.png" if "080" in roll_no else f"static/images/{roll_no_without_prefix}.jpg"
                if os.path.exists(img_path):
                    image_url = img_path
                else:
                    image_url = None
                results.append({
                    'rollNo': roll_no,
                    'name': student.get('Name'),
                    'department': student.get('Department'),
                    'imagePath': image_url
                })
    
    return jsonify({
        'status': 'success',
        'results': results
    })
@app.route('/stop-processing')
def stop_processing():
    processing_status["active"] = False
    return redirect(url_for('index'))
@app.route('/get-images')
def get_images():
    gender = request.args.get('gender')
    dept = request.args.get('department')
    program = request.args.get('program')
    batch = request.args.get('batch')
    filtered_images = {}
    for roll_no, img_path in successful_images.items():
        student_info_key = f"PUL{roll_no}"
        student = get_student_info(student_info_key)
        include = True
        if gender and student.get('Gender') != gender:
            include = False
        if dept and student.get('Department') != dept:
            include = False  
        if program and student.get('ProgramType') != program:
            include = False
        if batch and roll_no[:3] != batch:
            include = False  
        if include:
            filtered_images[roll_no] = img_path
    return jsonify({
        'images': filtered_images,
        'status': {
            'total': processing_status["total"],
            'completed': processing_status["completed"],
            'active': processing_status["active"]
        }
    })
@app.route('/get-student-details/<roll_no>')
def get_student_details(roll_no):
    if not roll_no.startswith('PUL'):
        pul_roll_number = f"PUL{roll_no}"
    else:
        pul_roll_number = roll_no
    student_data = get_student_info(pul_roll_number)
    if student_data:
        return jsonify({
            'status': 'success',
            'data': student_data
        })
    else:
        return jsonify({
            'status': 'error',
            'message': f'No details found for student with roll number {roll_no}'
        })

@app.route('/get-filter-options')
def get_filter_options():
    departments = set()
    genders = set()
    programs = set()
    batches = set()
    for roll_no, student in all_students.items():
        if student.get('Department'):
            departments.add(student.get('Department'))
        if student.get('Gender'):
            genders.add(student.get('Gender'))
        if student.get('ProgramType'):
            programs.add(student.get('ProgramType'))
        if roll_no and len(roll_no) >= 6:
            batch = roll_no[3:6] 
            if batch.isdigit():
                batches.add(batch)
    return jsonify({
        'departments': list(departments),
        'genders': list(genders),
        'programs': list(programs),
        'batches': list(batches)
    })
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

    
if __name__ == '__main__':
    for _ in range(5):
        worker_thread = threading.Thread(target=image_worker)
        worker_thread.daemon = True
        worker_thread.start()
    port = int(os.environ.get('PORT', 5000))  # default to 5000 for local dev
    app.run(host='0.0.0.0', port=port)
