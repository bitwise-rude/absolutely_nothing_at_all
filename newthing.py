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
def parse_student_data():
    all_students = {}
    pattern = r'PUL\d{3}(BCE|BEL|BCT|BEI|BME|BCH|BAS|BAR)\d{3}'
    roll_numbers = re.findall(pattern, all_data)
    lines = all_data.splitlines()
    for line in lines:
        for match in re.finditer(pattern, line):
            try:
                roll_no = match.group(0)
                roll_index = line.find(roll_no)
                section = line[roll_index + len(roll_no):]
                if "Civil Engineering" in section:
                    department = "Civil Engineering"
                elif "Electrical Engineering" in section:
                    department = "Electrical Engineering"
                elif "Computer Engineering" in section:
                    department = "Computer Engineering"
                elif "Electronics Engineering" in section:
                    department = "Electronics Engineering"
                elif "Mechanical Engineering" in section:
                    department = "Mechanical Engineering"
                elif "Chemical Engineering" in section:
                    department = "Chemical Engineering"
                elif "Architecture" in section:
                    department = "Architecture"
                elif "Aerospace" in section:
                    department = "Aerospace"
                else:
                    dept_match = re.search(r'(BCE|BEL|BCT|BEI|BME|BCH|BAS|BAR)', roll_no)
                    dept_code = dept_match.group() if dept_match else None
                    dept_names = {
                        'BCE': 'Civil Engineering',
                        'BEL': 'Electrical Engineering',
                        'BCT': 'Computer Engineering',
                        'BEI': 'Electronics Engineering',
                        'BME': 'Mechanical Engineering',
                        'BCH': 'Chemical Engineering',
                        'BAS': 'Aerospace',
                        "BAR" :"Architecture"
                    }
                    department = dept_names.get(dept_code, None)
                program_type = None
                if "Reular" in section[:50]:
                    program_type = "Regular"
                elif "Full Fee" in section[:50]:
                    program_type = "Full Fee"
                words = section.split()
                date_pattern = r'\d{1,2}/\d{1,2}/\d{4}'
                date_match = re.search(date_pattern, section)
                if date_match:
                    date_pos = date_match.start()
                    name_section = section[:date_pos].strip()
                    name_words = re.findall(r'[A-Z]+(?:\s+[A-Z]+)*', name_section)
                    if len(name_words) >= 2:    
                        name = name_words[-1].strip()
                    else:
                        name = None
                else:
                    name = None
                gender = None
                if "Male" in section:
                    gender = "Male"
                elif "Female" in section:
                    gender = "Female"
                dob = date_match.group() if date_match else None
                phone_match = re.search(r'\b\d{10}\b', section)
                phone = phone_match.group() if phone_match else None
                all_students[roll_no] = {
                    'Name': name,
                    'Gender': gender,
                    'DOB': dob,
                    'Phone': phone,
                    'Department': department,
                    'ProgramType': program_type,
                    'RollNo': roll_no
                }
            except Exception as e:
                print(f"Error parsing data for line with {roll_no}: {e}")
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
with open('templates/index.html', 'w') as f:
    f.write('''
            <!--ko khate mero code pardna ayo pheri khate ja uta -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Student Profile Gallery</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        .controls {
            display: flex;
            gap: 10px;
        }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn-primary {
            background-color: #4CAF50;
            color: white;
        }
        .btn-danger {
            background-color: #f44336;
            color: white;
        }
        .progress {
            height: 20px;
            width: 100%;
            background-color: #e0e0e0;
            border-radius: 5px;
            margin: 10px 0;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background-color: #4CAF50;
            text-align: center;
            line-height: 20px;
            color: white;
            transition: width 0.3s;
        }
        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .image-container {
            position: relative;
            cursor: pointer;
            border-radius: 5px;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: transform 0.2s;
            background-color: #eee;
            height: 150px; /* Fixed height to match image */
        }
        .image-container:hover {
            transform: translateY(-5px);
        }
        .image-container img {
            width: 100%;
            height: 150px;
            object-fit: cover;
            display: block;
        }
        .roll-no-overlay {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: rgba(0,0,0,0.7);
            color: white;
            text-align: center;
            padding: 5px;
            transform: translateY(100%);
            transition: transform 0.3s;
        }
        .image-container:hover .roll-no-overlay {
            transform: translateY(0);
        }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.7);
            align-items: center;
            justify-content: center;
            z-index: 100;
        }
        .modal-content {
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            text-align: center;
            max-width: 80%;
            max-height: 90vh;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }
        .modal-image-container {
            margin-bottom: 20px;
        }
        .modal img {
            max-width: 100%;
            max-height: 300px;
        }
        .close {
            position: absolute;
            top: 10px;
            right: 20px;
            font-size: 30px;
            cursor: pointer;
            color: white;
        }
        .image-error {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100%;
            color: #666;
            font-size: 12px;
            text-align: center;
            padding: 5px;
        }
        .student-details {
            width: 100%;
            text-align: left;
            margin-top: 20px;
        }
        .student-details table {
            width: 100%;
            border-collapse: collapse;
        }
        .student-details th, .student-details td {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: left;
        }
        .student-details th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        .student-details tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .loading-details {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .search-container {
            margin: 20px 0;
            display: flex;
            gap: 10px;
        }
        .search-input {
            flex-grow: 1;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .search-btn {
            padding: 8px 16px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        .filters {
            display: flex;
            gap: 10px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .filter-select {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            min-width: 150px;
        }
        .filter-btn {
            padding: 8px 16px;
            background-color: #2196F3;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Student Profile Gallery</h1>
        <div class="controls">
            <a href="/start-processing" class="btn btn-primary">Start Processing</a>
            <a href="/stop-processing" class="btn btn-danger">Stop Processing</a>
        </div>
    </div> 
    <div class="search-container">
        <input type="text" id="search-input" class="search-input" placeholder="Search By Name or Roll Number">

        <button id="search-btn" class="search-btn">Search</button>

   
    </div>
         <div class="face-search-container" style="margin-top: 20px; border: 1px solid #ddd; padding: 15px; border-radius: 5px; background-color: #f9f9f9;">
    <h3>Search by Face</h3>
    <form id="face-upload-form" enctype="multipart/form-data">
        <div style="display: flex; gap: 10px; align-items: center;">
            <input type="file" id="face-input" accept="image/*" style="flex-grow: 1;">
            <button type="submit" class="btn btn-primary">Find Matches</button>
        </div>
    </form>
    <div id="face-preview" style="margin-top: 10px; display: none;">
        <h4>Uploaded Image:</h4>
        <img id="preview-image" style="max-width: 200px; max-height: 200px; margin-top: 10px;">
    </div>
    <div id="face-results" style="margin-top: 20px; display: none;">
        <h4>Top Matches:</h4>
        <div id="face-results-container" class="gallery" style="grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));">
        </div>
    </div>
</div>
<div class="filters">
    <select id="gender-filter" class="filter-select">
        <option value="">All Genders</option>
    </select>
    <select id="department-filter" class="filter-select">
        <option value="">All Departments</option>
    </select>
    
    <select id="program-filter" class="filter-select">
        <option value="">All Programs</option>
    </select>
    <select id="batch-filter" class="filter-select">
        <option value="">All Batches</option>
    </select>
    <button id="apply-filters" class="filter-btn">Apply Filters</button>
    <button id="reset-filters" class="filter-btn">Reset Filters</button>
</div>
    <div class="status">
        <div class="progress">
            <div id="progress-bar" class="progress-bar" style="width: 0%">0%</div>
        </div>
        <p id="status-text">Ready to start processing...</p>
    </div>
    <div class="gallery" id="gallery">
    </div>
    <div class="modal" id="image-modal">
        <span class="close" id="close-modal">&times;</span>
        <div class="modal-content">
            <h2 id="modal-roll-no"></h2>
            <div class="modal-image-container">
                <img id="modal-image" src="" alt="Student Profile">
            </div>
            <div id="student-details" class="student-details">
                <div id="loading-details" class="loading-details">Loading student details...</div>
                <table id="details-table" style="display: none;">
                    <tbody>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        function loadFilterOptions() {
    fetch('/get-filter-options')
        .then(response => response.json())
        .then(data => {
            const genderFilter = document.getElementById('gender-filter');
            const departmentFilter = document.getElementById('department-filter');
            const programFilter = document.getElementById('program-filter');
            const batchFilter = document.getElementById('batch-filter');
            genderFilter.options.length = 1;
            departmentFilter.options.length = 1;
            programFilter.options.length = 1;
            batchFilter.options.length = 1;
            data.genders.forEach(gender => {
                const option = document.createElement('option');
                option.value = gender;
                option.textContent = gender;
                genderFilter.appendChild(option);
            });
            data.departments.forEach(department => {
                const option = document.createElement('option');
                option.value = department;
                option.textContent = department;
                departmentFilter.appendChild(option);
            });
            data.programs.forEach(program => {
                const option = document.createElement('option');
                option.value = program;
                option.textContent = program;
                programFilter.appendChild(option);
            });
            data.batches.forEach(batch => {
                const option = document.createElement('option');
                option.value = batch;
                option.textContent = "Batch " + batch;
                batchFilter.appendChild(option);
            });
        })
        .catch(error => console.error('Error loading filter options:', error));
}
        function updateGallery() {
            const gender = document.getElementById('gender-filter').value;
            const department = document.getElementById('department-filter').value;
            const program = document.getElementById('program-filter').value;
                const batch = document.getElementById('batch-filter').value;
            let url = '/get-images';
            const params = new URLSearchParams();
            if (gender) params.append('gender', gender);
            if (department) params.append('department', department);
            if (program) params.append('program', program);
            if (batch) params.append('batch', batch);
            if (params.toString()) {
                url += '?' + params.toString();
            }
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    const gallery = document.getElementById('gallery');
                    const images = data.images;
                    const status = data.status;
                    
                    const progressPercent = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;
                    document.getElementById('progress-bar').style.width = progressPercent + '%';
                    document.getElementById('progress-bar').textContent = progressPercent + '%';
                    
                    document.getElementById('status-text').textContent = 
                        `Processing: ${status.active ? 'Active' : 'Stopped'} | ` +
                        `Completed: ${status.completed} / ${status.total} | ` +
                        `Found: ${Object.keys(images).length} images`;
                    
                    gallery.innerHTML = '';

                    const sortedEntries = Object.entries(images).sort((a, b) => {
    const batchA = a[0].substring(0, 3);
    const batchB = b[0].substring(0, 3);
    
    if (batchA === '081' && batchB !== '081') return -1;
    if (batchA !== '081' && batchB === '081') return 1;
    if (batchA === '080' && batchB !== '080' && batchB !== '081') return -1;
    if (batchA !== '080' && batchA !== '081' && batchB === '080') return 1;
    
    return 0;
});
                    
                    for (const [rollNo, imagePath] of sortedEntries) {
                        const container = document.createElement('div');
                        container.className = 'image-container';
                        
                        const imgHtml = `
                            <img src="/${imagePath}" alt="Student ${rollNo}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                            <div class="image-error" style="display:none;">Image not available</div>
                            <div class="roll-no-overlay">${rollNo}</div>
                        `;
                        
                        container.innerHTML = imgHtml;
                        container.addEventListener('click', () => showModal(rollNo, `/${imagePath}`));
                        gallery.appendChild(container);
                    }
                })
                .catch(error => console.error('Error fetching images:', error));
        }
        function fetchStudentDetails(rollNo) {
            document.getElementById('loading-details').style.display = 'block';
            document.getElementById('loading-details').textContent = 'Loading student information...';
            document.getElementById('details-table').style.display = 'none';
            
            fetch(`/get-student-details/${rollNo}`)
                .then(response => response.json())
                .then(data => {
                    const detailsTable = document.getElementById('details-table');
                    const loadingDetails = document.getElementById('loading-details');
                    
                    if (data.status === 'success') {
                        detailsTable.innerHTML = '';
                        
                        const headerRow = document.createElement('tr');
                        headerRow.innerHTML = '<th>Field</th><th>Value</th>';
                        detailsTable.appendChild(headerRow);
                        
                        for (const [key, value] of Object.entries(data.data)) {
                            if (value && String(value).trim() !== '') {
                                const row = document.createElement('tr');
                                row.innerHTML = `
                                    <td>${key}</td>
                                    <td>${value}</td>
                                `;
                                detailsTable.appendChild(row);
                            }
                        }  
                        loadingDetails.style.display = 'none';
                        detailsTable.style.display = 'table';
                    } else {
                        loadingDetails.textContent = data.message || 'No details found for this student';
                    }
                })
                .catch(error => {
                    console.error('Error fetching student details:', error);
                    document.getElementById('loading-details').textContent = 'Error loading student details';
                });
        }
 function showModal(rollNo, imagePath) {
    const modal = document.getElementById('image-modal');
    const modalImage = document.getElementById('modal-image');
    const modalRollNo = document.getElementById('modal-roll-no');
    const imageContainer = document.querySelector('.modal-image-container');
    modalRollNo.textContent = 'Roll Number: ' + rollNo;
    if (imagePath) {
        modalImage.src = imagePath;
        modalImage.style.display = 'block';
        modalImage.onerror = function() {
            this.style.display = 'none';
            imageContainer.innerHTML += '<div class="image-error" style="padding: 30px;">Image not available</div>';
        };
    } else {
        modalImage.style.display = 'none';
        imageContainer.innerHTML = '<div class="image-error" style="padding: 30px;">Image not available</div>';
    }
    
    fetchStudentDetails(rollNo);
    modal.style.display = 'flex';
}   
function searchStudent() {
    const searchInput = document.getElementById('search-input');
    const searchTerm = searchInput.value.trim().toUpperCase();
    if (!searchTerm) return;
const isRollNumber = /(?:\d{3}[A-Z]{3}\d{3})/i.test(searchTerm);
    console.log(searchTerm);
    if (isRollNumber) {
        let rollNoToUse = searchTerm;
        if (!searchTerm.startsWith('PUL') && searchTerm.length === 6) {
            rollNoToUse = `PUL${searchTerm}`;
        }
        fetch(`/get-student-details/${rollNoToUse}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    const rollNoWithoutPrefix = rollNoToUse.replace('PUL', '');
                    fetch('/get-images')
                        .then(response => response.json())
                        .then(imageData => {
                            const imagePath = imageData.images[rollNoWithoutPrefix];
                            showModal(rollNoToUse, imagePath ? `/${imagePath}` : '');
                        })
                        .catch(error => {
                            console.error('Error fetching image:', error);
                            showModal(rollNoToUse, '');
                        });
                } else {
                    alert('No student found with this roll number');
                }
            })
            .catch(error => {
                console.error('Error searching by roll number:', error);
                alert('Error searching. Please try again.');
            });
    } else {
        searchByName(searchTerm);
    }
}
function searchByName(name) {
    name = name.trim().toUpperCase();
    if (!name) return;

    // Use the existing search API endpoint instead of manually checking all images
    fetch(`/search-students?term=${encodeURIComponent(name)}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.results.length > 0) {
                const students = data.results;
                
                if (students.length === 1) {
                    // If only one student found, show their modal directly
                    showModal(students[0].rollNo, students[0].imagePath ? `/${students[0].imagePath}` : null);
                } else {
                    // If multiple students found, show selection modal
                    showStudentSelectionModal(students.map(student => ({
                        rollNo: student.rollNo,
                        imagePath: student.imagePath,
                        name: student.name || 'Unknown'
                    })));
                }
            } else {
                alert('No students found with this name');
            }
        })
        .catch(error => {
            console.error('Error searching by name:', error);
            alert('Error searching. Please try again.');
        });
}
function showStudentSelectionModal(students) {
    const selectionModal = document.createElement('div');
    selectionModal.className = 'modal';
    selectionModal.style.display = 'flex';
    selectionModal.innerHTML = `
        <div class="modal-content" style="width: 80%; max-width: 600px;">
            <h2>Multiple Students Found</h2>
            <p>Please select a student:</p>
            <div class="student-list" style="max-height: 400px; overflow-y: auto;"></div>
            <button class="btn btn-danger" style="margin-top: 15px;">Cancel</button>
        </div>
    `;
    const studentList = selectionModal.querySelector('.student-list');
    students.forEach(student => {
        const studentItem = document.createElement('div');
        studentItem.style.cssText = 'display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #ddd; cursor: pointer;';
        let imgHtml = '';
        if (student.imagePath) {
            imgHtml = `<img src="/${student.imagePath}" style="width: 50px; height: 50px; margin-right: 15px; object-fit: cover;">`;
        } else {
            imgHtml = `<div style="width: 50px; height: 50px; margin-right: 15px; background-color: #eee; display: flex; align-items: center; justify-content: center;">No img</div>`;
        }
        studentItem.innerHTML = `
            ${imgHtml}
            <div>
                <div><strong>${student.name}</strong></div>
                <div>${student.rollNo}</div>
            </div>
        `;
        studentItem.addEventListener('click', () => {
            document.body.removeChild(selectionModal);
            showModal(student.rollNo, student.imagePath ? `/${student.imagePath}` : '');
        });
        studentList.appendChild(studentItem);
    });
    selectionModal.querySelector('button').addEventListener('click', () => {
        document.body.removeChild(selectionModal);
    });
    document.body.appendChild(selectionModal);
}
        document.getElementById('close-modal').addEventListener('click', () => {
            document.getElementById('image-modal').style.display = 'none';
        });
        window.addEventListener('click', (event) => {
            const modal = document.getElementById('image-modal');
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
        document.getElementById('apply-filters').addEventListener('click', updateGallery);
        document.getElementById('reset-filters').addEventListener('click', () => {
    document.getElementById('gender-filter').value = '';
    document.getElementById('department-filter').value = '';
    document.getElementById('program-filter').value = '';
    document.getElementById('batch-filter').value = '';
    updateGallery();
});
        document.getElementById('search-btn').addEventListener('click', searchStudent);
        document.getElementById('search-input').addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                searchStudent();
            }
        });
        setInterval(updateGallery, 5000);
        loadFilterOptions();
        updateGallery();

        document.getElementById('face-input').addEventListener('change', function(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const previewImg = document.getElementById('preview-image');
            previewImg.src = e.target.result;
            document.getElementById('face-preview').style.display = 'block';
            document.getElementById('face-results').style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
});
document.getElementById('face-upload-form').addEventListener('submit', function(event) {
    event.preventDefault();
    
    const fileInput = document.getElementById('face-input');
    if (!fileInput.files.length) {
        alert('Please select an image to upload');
        return;
    }
    
    const formData = new FormData();
    formData.append('image', fileInput.files[0]);
    const resultsContainer = document.getElementById('face-results-container');
    resultsContainer.innerHTML = '<div style="grid-column: 1 / -1; text-align: center;">Processing image...</div>';
    document.getElementById('face-results').style.display = 'block';
    
    fetch('/search-by-face', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        resultsContainer.innerHTML = '';
        
        if (data.status === 'success' && data.matches.length > 0) {
            data.matches.forEach(match => {
                const container = document.createElement('div');
                container.className = 'image-container';
                container.style.height = 'auto';
                
                const matchHtml = `
                    <img src="/${match.imagePath}" alt="Student ${match.rollNo}" 
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                    <div class="image-error" style="display:none;">Image not available</div>
                    <div style="padding: 5px; text-align: center;">
                        <div>${match.name || 'Unknown'}</div>
                        <div>${match.rollNo}</div>
                        <div>Match: ${Math.round(match.confidence * 100)}%</div>
                    </div>
                `;
                
                container.innerHTML = matchHtml;
                container.addEventListener('click', () => showModal(match.rollNo, `/${match.imagePath}`));
                resultsContainer.appendChild(container);
            });
        } else {
            resultsContainer.innerHTML = '<div style="grid-column: 1 / -1; text-align: center;">No matching faces found</div>';
        }
    })
    .catch(error => {
        console.error('Error searching by face:', error);
        resultsContainer.innerHTML = '<div style="grid-column: 1 / -1; text-align: center;">Error processing image</div>';
    });
});
    </script>
</body>
</html>
''')
if __name__ == '__main__':
    for _ in range(5):
        worker_thread = threading.Thread(target=image_worker)
        worker_thread.daemon = True
        worker_thread.start()
    port = int(os.environ.get('PORT', 5000))  # default to 5000 for local dev
    app.run(host='0.0.0.0', port=port)
