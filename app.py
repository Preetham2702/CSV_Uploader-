from flask import Flask, render_template, request, redirect, url_for, session
import os
import pandas as pd
import psycopg2
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cv2
import numpy as np
import imageio
from uuid import uuid4
import io
from PIL import Image

app = Flask(__name__)
app.secret_key = 'supersecretkey'

UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'uploads'))
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5 GB
os.environ["IMAGEIO_FFMPEG_EXE"] = "/opt/homebrew/bin/ffmpeg"

hostname = 'localhost'
database = 'postgres'
username = 'postgres'
pwd = 'Srinivas@123'
port_id = '5340'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET', 'POST'])
def main_page():
    return render_template('main.html')

@app.route('/handle_stage_selection', methods=['POST'])
def handle_stage_selection():
    stage = request.form['stage']

    if stage == 'in_process':
        return redirect(url_for('select_sensor'))
    elif stage == 'design_stage':
        return redirect(url_for('machine', stage='design_stage'))
    elif stage == 'post_process':
        return redirect(url_for('machine', stage='post_process'))
    else:
        return "Invalid selection"

@app.route('/select_sensor', methods=['GET', 'POST'])
def select_sensor():
    return render_template('select_sensor.html')

@app.route('/handle_sensor_selection', methods=['POST'])
def handle_sensor_selection():
    sensor = request.form['sensor']

    if sensor == 'sensor1':
        return "Sensor 1 page coming soon."
    elif sensor == 'sensor2':
        return "Sensor 2 page coming soon."
    elif sensor == 'sensor3':
        return redirect(url_for('sensor3_subtype'))
    else:
        return "Invalid sensor"

@app.route('/sensor3_subtype', methods=['GET', 'POST'])
def sensor3_subtype():
    return render_template('sensor3.html')

@app.route('/handle_sensor3_type', methods=['POST'])
def handle_sensor3_type():
    subtype = request.form['type']

    if subtype == 'ircamera':
        return redirect(url_for('machine', stage='ircamera'))
    elif subtype == 'tdvideo':
        return "tdvedio page comming soon"
    elif subtype == 'tdimage':
        return "tdimage page comming soon"
    else:
        return "Invalid sensor3 subtype"

@app.route('/machine', methods=['GET', 'POST'])
def machine():
    stage = request.args.get('stage') or request.form.get('stage')
    conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
    cur = conn.cursor()
    
    # Check if material exists
    cur.execute("SELECT mat_id, mat_name FROM material")
    materials = cur.fetchall()

    if not materials:  # No materials in DB
        cur.close()
        conn.close()
        return redirect(url_for('add_material',stage=stage))  # redirect to add_material page

    if request.method == 'POST':
        machine_id = int(request.form['machine_id'])
        machine_name = request.form['machine_name']
        material_id = int(request.form['material_id'])
        deposit_id = int(request.form['deposit_id'])
        
        # store in session
        session['machine_id'] = machine_id
        session['material_id'] = material_id
        session['deposit_id'] = deposit_id
        session['stage'] = stage

        try:
            cur.execute("""
                INSERT INTO Machine (m_id, m_name)
                VALUES (%s, %s)
                ON CONFLICT (m_id) DO NOTHING
            """, (machine_id, machine_name))

            conn.commit()

        except Exception as e:
            return f"Error: {e}"
        finally:
            cur.close()
            conn.close()

        if stage == 'design_stage':
            return redirect(url_for('design_stage',deposit_id=deposit_id, stage=stage, machine_id=machine_id, material_id=material_id))
        elif stage == 'post_process':
            return redirect(url_for('post_process', deposit_id=deposit_id, stage=stage, machine_id=machine_id, material_id=material_id))
        else:
            return redirect(url_for('index', deposit_id=deposit_id,stage=stage, machine_id=machine_id, material_id=material_id))

    # Pass materials list to your machine.html template
    return render_template('machine.html', materials=materials, stage=stage)
    

@app.route('/add_material', methods=['GET', 'POST'])
def add_material():
    stage = request.args.get('stage') or request.form.get('stage')
    materials= []
    try:
        conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
        cur = conn.cursor()

        if request.method == 'POST':
            material_name = request.form['material_name']

            try:
                cur.execute("INSERT INTO material (mat_name) VALUES (%s)", (material_name,))
                conn.commit()

            except Exception as e:
                return f"Error inserting values {e}"


            # Load material table to show in the table:
        cur.execute("SELECT mat_id, mat_name FROM material")
        materials = cur.fetchall()

    except Exception as e:
        return f"Error table not existing {e}"
    finally:
        cur.close()
        conn.close()

    return render_template('add_material.html', materials=materials, stage=stage)

@app.route('/index')
def index():
    machine_id = request.args.get('machine_id') or session.get('machine_id')
    material_id = request.args.get('material_id') or session.get('material_id')
    deposit_id = request.args.get('deposit_id') or session.get('deposit_id')
    stage = request.args.get('stage') or session.get('stage')
    message = request.args.get('message') 

    #if any are missing, return error
    if not stage or not machine_id or not material_id:
        return "Missing stage or machine/material ID"

    grouped_files = {}

    for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER']):
        files.sort()
        for file in files:
            rel_dir = os.path.relpath(root, app.config['UPLOAD_FOLDER'])
            rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file

            if rel_dir == '.':
                grouped_files.setdefault('', []).append(rel_file)
            else:
                folder = rel_dir.split(os.sep)[0]
                grouped_files.setdefault(folder, []).append(rel_file)

    return render_template('index.html', deposit_id=deposit_id,files=grouped_files,stage=stage,machine_id=machine_id,material_id=material_id,message=message)  # pass message to template

@app.route('/upload', methods=['POST'])
def upload_file():
    for file in request.files.getlist('files[]'):
        relative_path = file.filename
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], relative_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        file.save(save_path)
    return ('Files not selected')

@app.route('/design_stage', methods=['GET', 'POST'])
def design_stage():
    machine_id = request.args.get('machine_id')
    material_id = request.args.get('material_id')
    deposit_id = request.args.get('deposit_id') or session.get('deposit_id')
    stage = request.args.get('stage')

    if request.method == 'POST':
        machine_id = request.form.get('machine_id')
        material_id = request.form.get('material_id')
        stage = request.args.get('stage')

        if not machine_id or not material_id:
            return "Missing machine_id or material_id!"

        file_name = request.form.get('file_name')
        width = request.form.get('width')
        height = request.form.get('height')
        depth = request.form.get('depth')

        width = float(width) if width else None
        height = float(height) if height else None
        depth = float(depth) if depth else None

        try:
            conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM design_stage WHERE File_name = %s", (file_name,))
            file_exists = cur.fetchone()[0]

            if file_exists > 0:
                # File already uploaded — show preview with message
                return render_template('design_stage.html',deposit_id=deposit_id,machine_id=machine_id,material_id=material_id,stage=stage,message="⚠️ File already uploaded!")
            
            cur.execute("INSERT INTO design_stage (deposit_id,file_name,width,height,depth,m_id, mat_id) VALUES (%s, %s, %s, %s, %s, %s,%s)", (deposit_id, file_name,width,height,depth,machine_id, material_id))

            conn.commit()

            return redirect(url_for('design_stage',deposit_id=deposit_id, stage=stage, machine_id=machine_id, material_id=material_id,message = 'Inserted values sucessfully'))

        except Exception as e:
            return f"Error inserting values {e}"

        finally:
            cur.close()
            conn.close()  

    return render_template("design_stage.html",deposit_id=deposit_id,stage=stage, machine_id=machine_id, material_id=material_id,message=request.args.get("message"))
        

@app.route('/preview_sensor1/<path:filename>')
def preview_sensor1(filename):
    return "Still in Process "

@app.route('/preview_sensor2/<path:filename>')
def preview_sensor2(filename):
    return "Still in Process "

def extract_ircamera_dataframe(filepath, expected_cols=20):
    with open(filepath, 'r') as file:
        lines = file.read().replace('\r', '').strip().split('\n')

    image_lines = []
    start_data = False

    for line in lines:
        line = line.strip()
        if not start_data:
            if "Image Data" in line:
                start_data = True
            continue
        if not line:
            continue


        parts = [p.strip() for p in line.split(';')]

        try:
            float_parts = [float(p) for p in parts if p != '']
            while len(float_parts) < expected_cols:
                float_parts.append(np.nan)
            image_lines.append(float_parts[:expected_cols])
        except ValueError:
            continue

    if not image_lines:
        raise ValueError("No valid numeric data found.")

    df = pd.DataFrame(image_lines)
    df.columns = [f"Col{i+1}" for i in range(expected_cols)]
    return df

@app.route('/preview_ircamera/<path:filename>')
def preview_ircamera(filename):
    machine_id = session.get('machine_id')
    material_id = session.get('material_id')
    deposit_id = session.get('deposit_id')
    stage = session.get('stage')

    if not machine_id or not material_id:
        machine_id = session.get('machine_id')
        material_id = session.get('material_id')

        # If still missing after fallback → error
    if not machine_id or not material_id:
        return "Missing machine_id or material_id!"

    safe_path = os.path.normpath(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    if not safe_path.startswith(app.config['UPLOAD_FOLDER']):
        return "Invalid file path!", 400

    try:
        df = extract_ircamera_dataframe(safe_path)
        df_html = df.to_html(classes='table table-bordered', index=False, escape=False)
        return render_template('preview_ircamera.html', tables=[df_html], deposit_id=deposit_id,filename=filename,show_button=True, machine_id=machine_id, material_id=material_id, stage='ircamera')

    except Exception as e:
        return f"Error: {e}", 500

@app.route('/view_ircamera/<path:filename>')
def view_ircamera(filename):
    # Get extra params from request.args (query string)
    stage = request.args.get('stage')
    machine_id = request.args.get('machine_id')
    material_id = request.args.get('material_id')


    safe_path = os.path.normpath(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    if not safe_path.startswith(app.config['UPLOAD_FOLDER']):
        return "Invalid file path!", 400

    try:
        df = extract_ircamera_dataframe(safe_path)  # You need to call your ircamera function here too!
        vmin, vmax = df.values.min(), df.values.max()

        def get_gradient_color(value):
            norm_val = (value - vmin) / (vmax - vmin)
            norm_val = max(0.0, min(1.0, norm_val))
            return plt.cm.plasma(norm_val)

        df_html = '<table class="table table-bordered" style="border-collapse: collapse;">'
        for row in df.values:
            df_html += '<tr>'
            for val in row:
                rgba = get_gradient_color(val)
                hex_color = matplotlib.colors.to_hex(rgba)
                df_html += f'<td style="background-color: {hex_color}; text-align: center;">{val:.2f}</td>'
            df_html += '</tr>'
        df_html += '</table>'


        return render_template('preview_ircamera.html', tables=[df_html], filename=filename, show_button=False, machine_id=machine_id, material_id=material_id, stage=stage)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/s3ircamera_update/<path:filename>', methods=['POST'])
def s3ircamera_update(filename):
    machine_id = session.get('machine_id')
    material_id = session.get('material_id')
    deposit_id = session.get('deposit_id')
    stage = session.get('stage')


    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try: 
        # Always extract dataframe first
        df = extract_ircamera_dataframe(filepath)
        df_html = df.to_html(classes='table table-bordered', index=False, escape=False)

        conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
        cur = conn.cursor()

        # Check if file already exists in in_process table
        cur.execute("SELECT COUNT(*) FROM in_process WHERE File_name = %s", (filename,))
        file_exists = cur.fetchone()[0]

        if file_exists > 0:
            # File already uploaded — show preview with message
            return render_template('preview_ircamera.html',tables=[df_html], deposit_id=deposit_id,filename=filename,show_button = False,machine_id=machine_id,material_id=material_id,stage=stage,message="⚠️ File already uploaded!")

        # Otherwise continue insertion
        cur.execute("""
            INSERT INTO in_process (deposit_id,File_name, Sensor_ID, m_id, mat_id, type)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (File_name) DO NOTHING
        """, (deposit_id, filename, 3, machine_id, material_id, 'IR_Camera'))

        cur.execute("""
            INSERT INTO sensor3 (file_name, sensor_id, type_id, type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (file_name) DO NOTHING
        """, (filename, 3, 1, 'IR_Camera'))

        for idx, row in df.iterrows():
            row_index = idx + 1
            values = [filename, 1, row_index] + [float(row[i]) if pd.notna(row[i]) else None for i in df.columns]
            cur.execute("""
                INSERT INTO s3_ircamera (
                    file_name, type_id, Row_Index,
                    Col1, Col2, Col3, Col4, Col5, Col6, Col7, Col8, Col9, Col10,
                    Col11, Col12, Col13, Col14, Col15, Col16, Col17, Col18, Col19, Col20
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (File_name, row_index) DO NOTHING
            """, values)

        conn.commit()

        if os.path.exists(filepath):
            os.remove(filepath)  

        # Show success message with preview
        return redirect(url_for('index', deposit_id=deposit_id,stage=stage, machine_id=machine_id, material_id=material_id, message="File uploaded successfully"))

    except Exception as e:
        return f"Error uploading to Sensor3_IRCameraData: {e}", 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/bulk_update/<path:folder>', methods=['POST'])
def bulk_update_folder(folder):
    machine_id = int(request.args.get('machine_id'))
    material_id = int(request.args.get('material_id'))
    deposit_id = session.get('deposit_id')
    stage = request.args.get('stage')

    base_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    all_files = sorted([
        os.path.join(base_path, file)
        for file in os.listdir(base_path)
        if file.endswith('.csv')
    ])
    success_count = 0
    fail_count = 0

    for filepath in all_files:
        filename = os.path.relpath(filepath, app.config['UPLOAD_FOLDER'])
        try:
            df = extract_ircamera_dataframe(filepath)

            conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
            cur = conn.cursor()

            # Check if already exists:
            cur.execute("SELECT COUNT(*) FROM in_process WHERE File_name = %s", (filename,))
            if cur.fetchone()[0] > 0:
                print(f"⚠️ Skipping {filename}: already uploaded.")
                cur.close()
                conn.close()
                continue

            # Insert into in_process
            cur.execute("""
                INSERT INTO in_process (deposit_id,File_name, Sensor_ID, m_id, mat_id, type)
                VALUES (%s, %s, %s, %s, %s,%s)
                ON CONFLICT (File_name) DO NOTHING
            """, (deposit_id,filename, 3, machine_id, material_id, 'IR_Camera'))

            # Insert into sensor3
            cur.execute("""
                INSERT INTO sensor3 (file_name, sensor_id, type_id, type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (file_name) DO NOTHING
            """, (filename, 3, 1, 'IR_Camera'))

            # Insert into S3_IRCamera
            for idx, row in df.iterrows():
                row_index = idx + 1
                values = [filename, 1, row_index] + [float(row[i]) for i in df.columns]
                cur.execute("""
                    INSERT INTO S3_IRCamera (
                        File_name, type_id, Row_Index,
                        Col1, Col2, Col3, Col4, Col5, Col6, Col7, Col8, Col9, Col10,
                        Col11, Col12, Col13, Col14, Col15, Col16, Col17, Col18, Col19, Col20
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (File_name, Row_Index) DO NOTHING
                """, values)

            conn.commit()
            cur.close()
            conn.close()

            os.remove(filepath)
            success_count += 1

        except ValueError as ve:
            print(f"⚠️ Skipping {filename}: {ve}")
            fail_count += 1

        except Exception as e:
            print(f"Error processing {filename}: {e}")
            fail_count += 1

    print(f"Bulk upload completed: {success_count} files uploaded, {fail_count} failed.")
    
    # Return just 204 → no reload. Frontend handles reload.
    return ('', 204)

@app.route('/preview_tdvideo/')
def preview_tdvideo():
    return "Still in Process "

@app.route('/preview_tdimage')
def preview_tdimage():
    return "Still in Process "

@app.route('/post_process', methods=['POST','GET'])
def post_process():
    machine_id = request.args.get('machine_id')
    material_id = request.args.get('material_id')
    stage = request.args.get('stage')
    deposit_id = session.get('deposit_id')
    

    if request.method == 'POST':
        machine_id = request.form.get('machine_id')
        material_id = request.form.get('material_id')
        stage = request.args.get('stage')
        file_name = request.form.get('file_name')
        deposit_id = request.form.get('deposit_id')
        hardness = request.form.get('hardness')
        uts = request.form.get('uts')


        hardness = float(hardness) if hardness else None
        uts = float(uts) if uts else None
        

        try:
            conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=pwd, port=port_id)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM post_process WHERE File_name = %s", (file_name,))
            file_exists = cur.fetchone()[0]

            if file_exists > 0:
                # File already uploaded — show preview with message
                return render_template('post_process.html',deposit_id=deposit_id, machine_id=machine_id,material_id=material_id,stage=stage,message="⚠️ File already uploaded!")
            

            cur.execute("""
                INSERT INTO post_process(deposit_id, file_name, hardness, uts, m_id, mat_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (deposit_id,file_name,hardness, uts, machine_id, material_id))
            conn.commit()

            return redirect(url_for('post_process',deposit_id=deposit_id,stage=stage, machine_id=machine_id, material_id=material_id,message = 'Inserted values sucessfully'))

        except Exception as e:
            return f"Error inserting values {e}"

        finally:
            cur.close()
            conn.close()  

            # Redirect to index with success message
    return render_template("post_process.html",deposit_id=deposit_id,stage=stage, machine_id=machine_id, material_id=material_id,message=request.args.get("message"))
        

@app.route('/generate_video/<path:folder>')
def generate_folder_video(folder):
    base_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    video_name = f"{folder.replace('/', '_')}_thermal_video.mp4"
    output_path = os.path.join("static", "videos", video_name)

    #  If video already exists, just serve it
    if os.path.exists(output_path):
        return redirect(url_for('static', filename=f"videos/{video_name}"))

    os.makedirs("static/videos", exist_ok=True)

    try:
        # Collect all CSV files recursively in folder
        csv_files = sorted([
            os.path.join(root, file)
            for root, _, files in os.walk(base_path)
            for file in files if file.endswith('.csv')
        ])

        if not csv_files:
            return "No CSV files found in folder", 404

        writer = imageio.get_writer(output_path, fps=40)

        for file in csv_files:
            try:
                df = extract_image_dataframe(file)
                df = df.apply(pd.to_numeric, errors='coerce').fillna(0)
                image = create_colored_image(df)
                writer.append_data(image)
            except Exception as e:
                print(f"Skipping {file}: {e}")
                continue

        writer.close()
        return redirect(url_for('static', filename=f"videos/{video_name}"))

    except Exception as e:
        print(f"Video generation failed: {e}")
        return f"Error: {e}", 500

#having some errors 
@app.route('/generate_video_top_level')
def generate_top_level_video():
    output_path = os.path.join("static", "videos", "top_level_video.mp4")

    # If video already exists, just serve it
    if os.path.exists(output_path):
        return redirect(url_for('static', filename=f"videos/{video_name}"))

    os.makedirs("static/videos", exist_ok=True)

    try:
        top_files = []
        base_path = app.config['UPLOAD_FOLDER']

        for file in os.listdir(base_path):
            if file.endswith('.csv'):
                top_files.append(os.path.join(base_path, file))

        top_files.sort()
        writer = imageio.get_writer(output_path, fps=10)

        for file in top_files:
            try:
                df = extract_image_dataframe(file)
                df = df.apply(pd.to_numeric, errors='coerce').fillna(0)
                image = create_colored_image(df)
                writer.append_data(image)
            except Exception as e:
                print(f"Skipping {file}: {e}")
                continue

        writer.close()
        return redirect(url_for('static', filename=f"videos/{video_name}"))

    except Exception as e:
        print(f"Top-level video generation failed: {e}")
        return f"Error: {e}", 500

def create_colored_image(df):
    fig, ax = plt.subplots()
    ax.imshow(df.values, cmap='plasma')  # 'plasma' works well for thermal
    ax.axis('off')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    image = Image.open(buf)
    return np.array(image)


@app.route('/clear_selected', methods=['POST'])
def clear_selected():
    stage = request.form.get('stage')
    machine_id = request.form.get('machine_id')
    material_id = request.form.get('material_id')

    selected_items = request.form.getlist('selected_files')

    for item in selected_items:
        full_path = os.path.normpath(os.path.join(app.config['UPLOAD_FOLDER'], item))

        if os.path.isdir(full_path):
            # Delete all files and subfolders in the folder
            for root, dirs, files in os.walk(full_path, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
            try:
                os.rmdir(full_path)
            except FileNotFoundError:
                pass

            # Delete corresponding video file if it exists
            video_name = f"{item.strip('/').replace('/', '_')}_thermal_video.mp4"
            video_path = os.path.join("static", "videos", video_name)
            if os.path.exists(video_path):
                os.remove(video_path)

        elif os.path.isfile(full_path):
            os.remove(full_path)

        # Clean up empty parent directories
        folder = os.path.dirname(full_path)
        while folder and folder != app.config['UPLOAD_FOLDER']:
            if os.path.exists(folder) and not os.listdir(folder):
                os.rmdir(folder)
                folder = os.path.dirname(folder)
            else:
                break

    return redirect(url_for('index', stage=stage, machine_id=machine_id, material_id=material_id))


@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)

        folder = os.path.dirname(file_path)
        while folder and folder != app.config['UPLOAD_FOLDER']:
            if not os.listdir(folder):
                os.rmdir(folder)
                folder = os.path.dirname(folder)
            else:
                break

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(port=5000, debug=True)


