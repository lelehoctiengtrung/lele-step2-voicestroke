import os
import json
import time
import subprocess
import urllib.request

def fetch_cred(filename):
    url = f"https://lele-orchestrator-hub.comics2909-1.workers.dev/api/credentials?token=fbac8f27fd1833c411f62ef2225a3cc9d50b3333&file={filename}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.read().decode('utf-8').strip()
    except Exception as e:
        print(f"Warning: Could not fetch credential {filename} from hub: {e}")
        return None

def run_kaggle_kernel():
    # 1. Fetch credentials from Hub (with fallback to env)
    username_1 = fetch_cred("kaggle_username_1") or "letruong2704"
    key_1 = fetch_cred("kaggle_key_1") or os.environ.get("KAGGLE_KEY", "")
    username_2 = fetch_cred("kaggle_username_2") or "fredericcomic1"
    key_2 = fetch_cred("kaggle_key_2") or ""

    accounts = []
    if username_1 and key_1:
        accounts.append((username_1, key_1))
    if username_2 and key_2:
        accounts.append((username_2, key_2))
        
    if not accounts:
        raise ValueError("No Kaggle credentials found!")

    pushed_successfully = False
    active_username = None
    kernel_slug = None

    for username, key in accounts:
        print(f"Attempting setup for Kaggle account: {username}...")
        kaggle_dir = os.path.expanduser("~/.kaggle")
        os.makedirs(kaggle_dir, exist_ok=True)
        
        kaggle_creds = {
            "username": username,
            "key": key
        }
        
        kaggle_json_path = os.path.join(kaggle_dir, "kaggle.json")
        with open(kaggle_json_path, "w", encoding="utf-8") as f:
            json.dump(kaggle_creds, f)
            
        os.chmod(kaggle_json_path, 0o600)
        print(f"✅ Configured Kaggle API credentials for {username}.")
        
        # Check if the kernel is currently running to prevent interruption
        kernel_slug = f"{username}/step2-voicestroke"
        try:
            status_res = subprocess.run(["kaggle", "kernels", "status", kernel_slug], capture_output=True, text=True, check=True)
            current_status = status_res.stdout.strip().lower()
            print(f"Current kernel status check: {current_status}")
            if "running" in current_status or "queued" in current_status:
                print("⚠️ Kaggle kernel is already running or queued! Skipping push to let the active run complete.")
                return True
        except Exception as e:
            print(f"Warning: Could not check current status: {e}")
            
        # Modify kernel-metadata.json dynamically to target this user
        push_dir = "Kaggle_Steps"
        if not os.path.exists(push_dir):
            push_dir = "."
            
        metadata_path = os.path.join(push_dir, "kernel-metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["id"] = kernel_slug
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            print(f"✏️ Updated kernel-metadata.json ID to {kernel_slug}")

        # Deploy and start Kaggle kernel
        print(f"🚀 Deploying and starting Kaggle kernel for {username}...")
        push_res = subprocess.run(["kaggle", "kernels", "push", "-p", push_dir], capture_output=True, text=True)
        
        stdout_output = push_res.stdout or ""
        stderr_output = push_res.stderr or ""
        print(stdout_output)
        if stderr_output:
            print(stderr_output)
            
        combined_output = (stdout_output + "\n" + stderr_output).lower()
        if "successfully pushed" in combined_output:
            print(f"✅ Kernel successfully pushed for account {username}!")
            pushed_successfully = True
            active_username = username
            break
        else:
            print(f"❌ Failed to push kernel for account {username}. Trying next account if available...")
            
    if not pushed_successfully:
        raise RuntimeError("Failed to push/trigger Kaggle kernel on all available accounts.")

    # 3. Wait for the kernel to transition to queued or running state first
    print("⏳ Waiting for Kaggle to register the new run...")
    transition_start = time.time()
    transitioned = False
    
    while time.time() - transition_start < 120:
        time.sleep(15)
        try:
            status_res = subprocess.run(["kaggle", "kernels", "status", kernel_slug], capture_output=True, text=True, check=True)
            output = status_res.stdout.strip()
            print(f"Initial transition check: {output}")
            output_lower = output.lower()
            if "queued" in output_lower or "running" in output_lower or "complete" in output_lower:
                print(f"⚡ Kaggle has registered the new run (status: {output}).")
                transitioned = True
                break
        except Exception as e:
            print(f"Warning during initial status check: {e}")
            
    if not transitioned:
        print("⚠️ Warning: Kernel status did not transition to queued/running after 2 minutes. Proceeding to monitor anyway...")

    # 4. Monitor run status
    print(f"🛰️ Monitoring Kaggle kernel '{kernel_slug}' (Timeout: 330 minutes)...")
    
    start_time = time.time()
    timeout = 19800
    
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
            elif "error" in output_lower or "cancel" in output_lower or "fail" in output_lower:
                print(f"❌ Kaggle kernel execution failed or was cancelled! Status: {output}")
                try:
                    subprocess.run(["kaggle", "kernels", "output", kernel_slug, "-p", "kaggle_output"])
                except Exception as ex:
                    print(f"Warning fetching output logs: {ex}")
                raise SystemExit("Kaggle kernel run failed.")
        except SystemExit:
            raise
        except Exception as e:
            print(f"Warning during status check: {e}")
            
    raise TimeoutError("Kaggle kernel run timed out.")

if __name__ == "__main__":
    run_kaggle_kernel()