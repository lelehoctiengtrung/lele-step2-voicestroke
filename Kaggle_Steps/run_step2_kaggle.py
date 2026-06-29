import os
import json
import time
import subprocess

def run_kaggle_kernel():
    # 1. Setup kaggle credentials
    kaggle_dir = os.path.expanduser("~/.kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    
    # Set username and key from environment variables (GitHub action secrets)
    kaggle_username = os.environ.get("KAGGLE_USERNAME", "letruong2704")
    kaggle_key = os.environ.get("KAGGLE_KEY", "")
    
    kaggle_creds = {
        "username": kaggle_username,
        "key": kaggle_key
    }
    
    kaggle_json_path = os.path.join(kaggle_dir, "kaggle.json")
    with open(kaggle_json_path, "w", encoding="utf-8") as f:
        json.dump(kaggle_creds, f)
        
    os.chmod(kaggle_json_path, 0o600)
    print("✅ Configured Kaggle API credentials.")
    
    # 2. Deploy and start Kaggle kernel
    print("🚀 Deploying and starting Kaggle kernel...")
    push_dir = "Kaggle_Steps"
    if not os.path.exists(push_dir):
        push_dir = "."
        
    subprocess.run(["kaggle", "kernels", "push", "-p", push_dir], check=True)
    
    kernel_slug = f"{kaggle_username}/step2-voicestroke"
    
    # 3. Wait for the kernel to transition to queued or running state first
    print("⏳ Waiting for Kaggle to register the new run and transition from previous 'complete' status...")
    transition_start = time.time()
    transitioned = False
    
    while time.time() - transition_start < 120:
        time.sleep(15)
        try:
            status_res = subprocess.run(["kaggle", "kernels", "status", kernel_slug], capture_output=True, text=True, check=True)
            output = status_res.stdout.strip()
            print(f"Initial transition check: {output}")
            output_lower = output.lower()
            if "complete" not in output_lower:
                print("⚡ Kaggle has registered the new run (status changed from complete).")
                transitioned = True
                break
        except Exception as e:
            print(f"Warning during initial status check: {e}")
            
    if not transitioned:
        print("⚠️ Warning: Kernel status did not transition away from 'complete' after 2 minutes. Proceeding to monitor anyway...")

    # 4. Monitor run status
    print(f"🛰️ Monitoring Kaggle kernel '{kernel_slug}' (Timeout: 120 minutes)...")
    
    start_time = time.time()
    timeout = 7200
    
    while time.time() - start_time < timeout:
        time.sleep(30)
        try:
            status_res = subprocess.run(["kaggle", "kernels", "status", kernel_slug], capture_output=True, text=True, check=True)
            output = status_res.stdout.strip()
            print(f"Status check: {output}")
            
            output_lower = output.lower()
            if "complete" in output_lower:
                print("🎉 Kaggle kernel execution completed successfully!")
                return True
            elif "error" in output_lower:
                print("❌ Kaggle kernel execution failed! Fetching logs...")
                subprocess.run(["kaggle", "kernels", "output", kernel_slug, "-p", "kaggle_output"])
                raise RuntimeError("Kaggle kernel run failed.")
        except Exception as e:
            print(f"Warning during status check: {e}")
            
    raise TimeoutError("Kaggle kernel run timed out.")

if __name__ == "__main__":
    run_kaggle_kernel()