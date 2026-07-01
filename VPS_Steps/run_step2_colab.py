import os
import sys
import json
import shutil
import subprocess
import time

# Add parent directory to path to allow importing telegram_notifier
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from VPS_Steps import telegram_notifier as tel
except ImportError:
    # Fallback in case of path structure changes
    tel = None

CONFIG_DIR = os.path.expanduser("~/.config/colab-cli")
ROTATED_DIR = os.path.join(CONFIG_DIR, "rotated_tokens")
TOKEN_JSON_PATH = os.path.join(CONFIG_DIR, "token.json")
BACKUP_PATH = os.path.join(CONFIG_DIR, "token.json.original_backup")

def send_telegram(msg):
    print(msg)
    if tel:
        try:
            tel.send_message(msg)
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")

def get_rotated_accounts():
    if not os.path.exists(ROTATED_DIR):
        print(f"⚠️ rotated_tokens directory not found at {ROTATED_DIR}")
        return []
    
    files = [f for f in os.listdir(ROTATED_DIR) if f.endswith(".json")]
    # Extract email and return list of tuples (email, path)
    accounts = []
    for f in sorted(files):
        email = f[:-5]
        accounts.append((email, os.path.join(ROTATED_DIR, f)))
    return accounts

def switch_to_account(email, filepath):
    print(f"\n🔄 Switching Colab CLI to account: {email}")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    shutil.copy2(filepath, TOKEN_JSON_PATH)
    
    # Run a simple sessions command to refresh the token if needed
    try:
        res = subprocess.run(["colab", "sessions"], capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            # Copy refreshed token back to rotated_tokens to keep it updated
            shutil.copy2(TOKEN_JSON_PATH, filepath)
            print(f"✅ Successfully authenticated and refreshed token for {email}")
            return True
        else:
            print(f"❌ Failed to verify/refresh token for {email}. Stderr: {res.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error verifying account {email}: {e}")
        return False

def clean_up_session(session_name="step2-session"):
    print(f"🧹 Cleaning up any existing session named '{session_name}'...")
    try:
        subprocess.run(["colab", "stop", "-s", session_name], capture_output=True, text=True, timeout=30)
    except Exception:
        pass

def run_colab_workflow():
    session_name = "step2-session"
    notebook_path = "Kaggle_Steps/step2_voice_stroke.ipynb"
    
    if not os.path.exists(notebook_path):
        notebook_path = "./step2_voice_stroke.ipynb"
        if not os.path.exists(notebook_path):
            raise FileNotFoundError(f"Notebook not found at Kaggle_Steps/step2_voice_stroke.ipynb or {notebook_path}")

    accounts = get_rotated_accounts()
    if not accounts:
        send_telegram("⚠️ <b>[Colab Step 2]</b> Không tìm thấy danh sách tài khoản rotated_tokens để chạy dự phòng!")
        sys.exit(1)
        
    # Backup original token.json if it exists and hasn't been backed up yet
    if os.path.exists(TOKEN_JSON_PATH) and not os.path.exists(BACKUP_PATH):
        shutil.copy2(TOKEN_JSON_PATH, BACKUP_PATH)
        print("💾 Backed up original token.json")

    allocated_email = None
    allocated_gpu = False
    
    # Phase 1: Try allocating GPU session across all accounts
    send_telegram(f"🎙️ <b>[Colab Step 2]</b> Bắt đầu tìm kiếm tài khoản để khởi tạo Colab GPU (T4)...")
    for email, path in accounts:
        if not switch_to_account(email, path):
            continue
            
        clean_up_session(session_name)
        
        print(f"🚀 Attempting to create GPU session on {email}...")
        try:
            cmd = ["colab", "new", "--gpu", "T4", "-s", session_name]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            stdout = res.stdout or ""
            stderr = res.stderr or ""
            combined = (stdout + "\n" + stderr).lower()
            
            if res.returncode == 0 and "allocated" in combined or "created" in combined or "active" in combined or not any(x in combined for x in ["quota", "limit", "rate", "resource", "exhausted", "error"]):
                send_telegram(f"✅ <b>[Colab Step 2]</b> Khởi tạo thành công GPU session trên tài khoản: <code>{email}</code>")
                allocated_email = email
                allocated_gpu = True
                break
            else:
                print(f"⚠️ Failed to allocate GPU on {email}. Output: {stdout.strip()} | {stderr.strip()}")
                clean_up_session(session_name)
        except Exception as e:
            print(f"⚠️ Exception during GPU allocation on {email}: {e}")
            clean_up_session(session_name)

    # Phase 2: Fallback to CPU if GPU failed on all accounts
    if not allocated_email:
        send_telegram("⚠️ <b>[Colab Step 2]</b> Hết hạn mức GPU trên tất cả các tài khoản. Chuyển sang phương án dự phòng chạy CPU...")
        for email, path in accounts:
            if not switch_to_account(email, path):
                continue
                
            clean_up_session(session_name)
            
            print(f"🚀 Attempting to create CPU session on {email}...")
            try:
                cmd = ["colab", "new", "-s", session_name]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                stdout = res.stdout or ""
                stderr = res.stderr or ""
                combined = (stdout + "\n" + stderr).lower()
                
                if res.returncode == 0:
                    send_telegram(f"✅ <b>[Colab Step 2]</b> Khởi tạo thành công CPU session trên tài khoản: <code>{email}</code>")
                    allocated_email = email
                    allocated_gpu = False
                    break
                else:
                    print(f"⚠️ Failed to allocate CPU on {email}. Output: {stdout.strip()} | {stderr.strip()}")
                    clean_up_session(session_name)
            except Exception as e:
                print(f"⚠️ Exception during CPU allocation on {email}: {e}")
                clean_up_session(session_name)

    if not allocated_email:
        send_telegram("❌ <b>[Colab Step 2]</b> Thất bại khởi tạo session (cả GPU và CPU) trên toàn bộ tài khoản Colab!")
        # Restore original token.json
        if os.path.exists(BACKUP_PATH):
            shutil.move(BACKUP_PATH, TOKEN_JSON_PATH)
        sys.exit(1)

    # Phase 3: Execute Notebook
    exec_success = False
    try:
        send_telegram(f"⏳ <b>[Colab Step 2]</b> Bắt đầu thực thi notebook <code>step2_voice_stroke.ipynb</code> trên Colab...")
        
        # We run the exec command with a high timeout (4 hours)
        cmd = ["colab", "exec", "-s", session_name, "-f", notebook_path, "--timeout", "14400.0"]
        
        # Using Popen to stream stdout/stderr in real time to console
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Read output line by line
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            
        process.wait()
        
        if process.returncode == 0:
            send_telegram(f"🎉 <b>[Colab Step 2]</b> Thực thi notebook hoàn tất thành công trên tài khoản <code>{allocated_email}</code>!")
            exec_success = True
        else:
            send_telegram(f"❌ <b>[Colab Step 2]</b> Thực thi notebook thất bại! Mã lỗi: {process.returncode}")
            
    except Exception as e:
        send_telegram(f"❌ <b>[Colab Step 2]</b> Lỗi hệ thống trong quá trình thực thi: {e}")
    finally:
        # Stop session to free resources
        print("\n⏹️ Terminating Colab VM session...")
        clean_up_session(session_name)
        
        # Restore original token.json
        if os.path.exists(BACKUP_PATH):
            shutil.move(BACKUP_PATH, TOKEN_JSON_PATH)
            print("💾 Restored original token.json")
            
    if not exec_success:
        sys.exit(1)

if __name__ == "__main__":
    run_colab_workflow()
