"""
DummyProx - Nested Proxmox Hypervisor Manager
Flask backend for managing nested Proxmox deployments
"""

import os
import re
import random
import time
import threading
import tempfile
import subprocess
from flask import Flask, jsonify, request
from flask_cors import CORS
from proxmoxer import ProxmoxAPI
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Proxmox ISO download URL pattern
PROXMOX_ISO_MIRROR = "http://download.proxmox.com/iso/"

app = Flask(__name__)
CORS(app)

# Store connection and deployment state
state = {
    "connected": False,
    "connection": None,
    "proxmox": None,
    "nested_vmid": None,
    "nested_vms": [],
    "status": "idle",
    "logs": []
}

# VM name themes - server/application focused
THEMES = {
    "databases": ["mongo", "postgres", "mysql", "redis", "elastic", "cassandra", "influx", "neo4j", "couch", "mariadb", "sqlite", "cockroach", "timescale", "clickhouse", "dynamo"],
    "webservers": ["nginx", "apache", "caddy", "traefik", "haproxy", "envoy", "varnish", "lighttpd", "tomcat", "jetty", "gunicorn", "uvicorn", "puma", "passenger", "httpd"],
    "messaging": ["kafka", "rabbit", "nats", "pulsar", "zeromq", "activemq", "mosquitto", "emqx", "redis-mq", "nsq", "celery", "sidekiq", "resque", "bull", "bee"],
    "monitoring": ["prometheus", "grafana", "datadog", "nagios", "zabbix", "influx", "telegraf", "jaeger", "zipkin", "sentry", "newrelic", "splunk", "logstash", "kibana", "fluentd"],
    "containers": ["docker", "podman", "containerd", "kubernetes", "nomad", "swarm", "rancher", "portainer", "harbor", "registry", "buildah", "skopeo", "crio", "runc", "lxc"]
}


def add_log(message):
    """Add a log message with timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    state["logs"].append(f"[{timestamp}] {message}")
    if len(state["logs"]) > 100:
        state["logs"] = state["logs"][-100:]


def get_random_theme():
    """Get a random theme name"""
    return random.choice(list(THEMES.keys()))


def generate_vm_names(count, theme=None):
    """Generate themed VM names"""
    if theme is None or theme not in THEMES:
        theme = get_random_theme()

    base_names = THEMES[theme][:count]
    return [f"{name}-{str(i+1).zfill(2)}" for i, name in enumerate(base_names)]


def get_latest_proxmox_iso():
    """Get the latest Proxmox VE ISO filename and URL from the mirror"""
    try:
        response = requests.get(PROXMOX_ISO_MIRROR, timeout=30)
        response.raise_for_status()

        # Find all proxmox-ve ISO links (not -debug, not torrents)
        pattern = r'proxmox-ve_(\d+\.\d+)-(\d+)\.iso'
        matches = re.findall(pattern, response.text)

        if not matches:
            return None, None

        # Sort by version and release number to get latest
        versions = [(f"proxmox-ve_{m[0]}-{m[1]}.iso", m[0], int(m[1])) for m in matches]
        versions.sort(key=lambda x: (x[1], x[2]), reverse=True)

        latest_iso = versions[0][0]
        return latest_iso, f"{PROXMOX_ISO_MIRROR}{latest_iso}"
    except Exception as e:
        add_log(f"Error fetching ISO list: {str(e)}")
        return None, None


def check_iso_exists(proxmox, node, storage, iso_name):
    """Check if an ISO already exists on the Proxmox storage"""
    try:
        content = proxmox.nodes(node).storage(storage).content.get()
        for item in content:
            if item.get("content") == "iso" and iso_name in item.get("volid", ""):
                return item.get("volid")
        return None
    except Exception:
        return None


def download_and_upload_iso(proxmox, node, storage, iso_url, iso_name):
    """Download ISO and upload to Proxmox storage"""
    add_log(f"Downloading {iso_name} from Proxmox mirror...")

    # Download to temp file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".iso") as tmp_file:
            response = requests.get(iso_url, stream=True, timeout=600)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (50 * 1024 * 1024) < 8192:  # Log every ~50MB
                    pct = int(downloaded / total_size * 100)
                    add_log(f"Download progress: {pct}%")

            tmp_file.flush()
            tmp_path = tmp_file.name
            add_log("Download complete, uploading to Proxmox...")

    except Exception as e:
        add_log(f"Download failed: {str(e)}")
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return None

    # Upload to Proxmox using direct API call
    try:
        # Get connection info from state
        conn = state.get("connection", {})
        host = conn.get("host")
        port = conn.get("port", 8006)

        # Get auth ticket from proxmox object
        ticket = proxmox.get_tokens()[0]
        csrf = proxmox.get_tokens()[1]

        upload_url = f"https://{host}:{port}/api2/json/nodes/{node}/storage/{storage}/upload"

        with open(tmp_path, 'rb') as f:
            files = {'filename': (iso_name, f, 'application/octet-stream')}
            data = {'content': 'iso'}
            headers = {'CSRFPreventionToken': csrf}
            cookies = {'PVEAuthCookie': ticket}

            resp = requests.post(
                upload_url,
                files=files,
                data=data,
                headers=headers,
                cookies=cookies,
                verify=False,
                timeout=600
            )
            resp.raise_for_status()

        add_log(f"ISO uploaded successfully to {storage}")
        return f"{storage}:iso/{iso_name}"
    except Exception as e:
        add_log(f"Upload failed: {str(e)}")
        return None
    finally:
        # Clean up temp file
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def ensure_proxmox_iso(proxmox, node, storage="local"):
    """Ensure Proxmox ISO is available, download if needed"""
    add_log("Checking for Proxmox VE ISO...")

    # Get latest ISO info
    iso_name, iso_url = get_latest_proxmox_iso()
    if not iso_name:
        add_log("Could not determine latest Proxmox ISO")
        return None

    add_log(f"Latest Proxmox VE ISO: {iso_name}")

    # Check if already exists
    existing = check_iso_exists(proxmox, node, storage, iso_name)
    if existing:
        add_log(f"ISO already available: {existing}")
        return existing

    # Download and upload
    add_log(f"ISO not found on server, downloading...")
    return download_and_upload_iso(proxmox, node, storage, iso_url, iso_name)


def create_answer_file(password="root", hostname="nested-proxmox"):
    """Create Proxmox automated installer answer file content"""
    # TOML format answer file for Proxmox VE 8.x automated installer
    answer_content = f'''[global]
keyboard = "en-us"
country = "us"
fqdn = "{hostname}.local"
mailto = "admin@local"
timezone = "UTC"
root_password = "{password}"

[network]
source = "from-dhcp"

[disk-setup]
filesystem = "ext4"
disk_list = ["sda"]
'''
    return answer_content


def create_and_upload_answer_iso(proxmox, node, storage, password="root", hostname="nested-proxmox"):
    """Create an ISO containing the answer file and upload to Proxmox"""
    add_log("Creating automated installer answer file...")

    iso_name = "proxmox-answer.iso"  # Changed name to force recreation with correct label

    # Check if already exists
    existing = check_iso_exists(proxmox, node, storage, iso_name)
    if existing:
        add_log(f"Answer ISO already available: {existing}")
        return existing

    tmp_dir = None
    iso_path = None

    try:
        # Create temp directory for ISO contents
        tmp_dir = tempfile.mkdtemp()
        answer_path = os.path.join(tmp_dir, "answer.toml")

        # Write answer file
        answer_content = create_answer_file(password, hostname)
        with open(answer_path, 'w') as f:
            f.write(answer_content)

        # Create ISO using genisoimage or mkisofs
        # IMPORTANT: Label must be "INTRUCTION" - this is an intentional typo
        # that Proxmox automated installer looks for
        iso_path = tempfile.mktemp(suffix=".iso")

        try:
            # Try genisoimage first (common on Debian/Ubuntu)
            subprocess.run([
                "genisoimage", "-o", iso_path,
                "-V", "INTRUCTION",
                "-r", "-J",
                tmp_dir
            ], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Try mkisofs as fallback
                subprocess.run([
                    "mkisofs", "-o", iso_path,
                    "-V", "INTRUCTION",
                    "-r", "-J",
                    tmp_dir
                ], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                add_log("Warning: Could not create answer ISO (genisoimage/mkisofs not available)")
                add_log("Automated installation not available - manual install required")
                return None

        add_log("Answer ISO created, uploading to Proxmox...")

        # Upload to Proxmox
        conn = state.get("connection", {})
        host = conn.get("host")
        port = conn.get("port", 8006)

        ticket = proxmox.get_tokens()[0]
        csrf = proxmox.get_tokens()[1]

        upload_url = f"https://{host}:{port}/api2/json/nodes/{node}/storage/{storage}/upload"

        with open(iso_path, 'rb') as f:
            files = {'filename': (iso_name, f, 'application/octet-stream')}
            data = {'content': 'iso'}
            headers = {'CSRFPreventionToken': csrf}
            cookies = {'PVEAuthCookie': ticket}

            resp = requests.post(
                upload_url,
                files=files,
                data=data,
                headers=headers,
                cookies=cookies,
                verify=False,
                timeout=60
            )
            resp.raise_for_status()

        add_log(f"Answer ISO uploaded successfully")
        return f"{storage}:iso/{iso_name}"

    except Exception as e:
        add_log(f"Failed to create answer ISO: {str(e)}")
        return None
    finally:
        # Cleanup
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
        if iso_path and os.path.exists(iso_path):
            try:
                os.unlink(iso_path)
            except Exception:
                pass


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"})


@app.route("/api/connect", methods=["POST"])
def connect():
    """Connect to Proxmox server"""
    data = request.json
    host = data.get("host")
    user = data.get("user")
    password = data.get("password")
    port = data.get("port", 8006)

    if not all([host, user, password]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        add_log(f"Connecting to Proxmox at {host}:{port}...")
        proxmox = ProxmoxAPI(
            host,
            user=user,
            password=password,
            port=port,
            verify_ssl=False
        )

        # Test connection by getting nodes
        nodes = proxmox.nodes.get()

        state["connected"] = True
        state["proxmox"] = proxmox
        state["connection"] = {
            "host": host,
            "user": user,
            "port": port
        }

        add_log(f"Connected successfully! Found {len(nodes)} node(s)")

        return jsonify({
            "status": "connected",
            "nodes": [n["node"] for n in nodes]
        })

    except Exception as e:
        add_log(f"Connection failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    """Disconnect from Proxmox server"""
    state["connected"] = False
    state["proxmox"] = None
    state["connection"] = None
    add_log("Disconnected from Proxmox server")
    return jsonify({"status": "disconnected"})


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get current status"""
    return jsonify({
        "connected": state["connected"],
        "connection": state["connection"],
        "nested_vmid": state["nested_vmid"],
        "nested_vms": state["nested_vms"],
        "status": state["status"],
        "logs": state["logs"][-20:]
    })


@app.route("/api/nodes", methods=["GET"])
def get_nodes():
    """Get available Proxmox nodes"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    try:
        nodes = state["proxmox"].nodes.get()
        return jsonify({"nodes": nodes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/templates", methods=["GET"])
def get_templates():
    """Get available VM templates"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    try:
        templates = []
        nodes = state["proxmox"].nodes.get()

        for node in nodes:
            node_name = node["node"]
            vms = state["proxmox"].nodes(node_name).qemu.get()
            for vm in vms:
                if vm.get("template", 0) == 1:
                    templates.append({
                        "vmid": vm["vmid"],
                        "name": vm.get("name", f"VM {vm['vmid']}"),
                        "node": node_name
                    })

        return jsonify({"templates": templates})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/storage", methods=["GET"])
def get_storage():
    """Get available storage"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    node = request.args.get("node")
    if not node:
        return jsonify({"error": "Node required"}), 400

    try:
        storage = state["proxmox"].nodes(node).storage.get()
        return jsonify({"storage": storage})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/isos", methods=["GET"])
def get_isos():
    """Get available ISO images"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    node = request.args.get("node")
    storage = request.args.get("storage", "local")

    if not node:
        return jsonify({"error": "Node required"}), 400

    try:
        content = state["proxmox"].nodes(node).storage(storage).content.get()
        isos = [c for c in content if c.get("content") == "iso"]
        return jsonify({"isos": isos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_nested_proxmox_task(config):
    """Background task to create nested Proxmox"""
    try:
        state["status"] = "creating_nested"
        proxmox = state["proxmox"]
        node = config["node"]

        add_log("Starting nested Proxmox creation...")

        # Automatically get/download latest Proxmox ISO
        iso_volid = ensure_proxmox_iso(proxmox, node, storage="local")
        if not iso_volid:
            add_log("ERROR: Could not obtain Proxmox ISO. Please upload manually.")
            state["status"] = "error"
            return

        # Create answer ISO for automated installation
        vm_name = config.get("name", "nested-proxmox")
        answer_iso = create_and_upload_answer_iso(
            proxmox, node, storage="local",
            password="root",  # Default root password for nested Proxmox
            hostname=vm_name
        )

        # Find next available VMID
        vmid = config.get("vmid")
        if not vmid:
            cluster_resources = proxmox.cluster.resources.get(type="vm")
            used_ids = [r["vmid"] for r in cluster_resources]
            vmid = max(used_ids) + 1 if used_ids else 100

        add_log(f"Using VMID: {vmid}")

        # Create the nested Proxmox VM
        # cpu=host passes through host CPU features including VMX/SVM for nested virt
        vm_config = {
            "vmid": vmid,
            "name": vm_name,
            "memory": config.get("memory", 16384),
            "cores": config.get("cores", 4),
            "sockets": 1,
            "cpu": "host",
            "net0": f"virtio,bridge={config.get('bridge', 'vmbr0')}",
            "scsihw": "virtio-scsi-single",
            "agent": "enabled=1",
        }

        # Add disk - strip 'G' suffix as Proxmox expects just the number for LVM
        # Use 'or' to handle empty string from frontend
        storage = config.get("storage") or "local-lvm"
        disk_size = (config.get("disk_size") or "100G").rstrip("Gg")
        vm_config["scsi0"] = f"{storage}:{disk_size}"

        # Attach the Proxmox installer ISO as primary CD-ROM
        vm_config["ide2"] = f"{iso_volid},media=cdrom"

        # Attach answer ISO as secondary CD-ROM for automated installation
        if answer_iso:
            vm_config["ide3"] = f"{answer_iso},media=cdrom"
            add_log("Automated installation configured with answer file")
        else:
            add_log("Manual installation required - answer ISO not available")

        # Boot from CD-ROM first
        vm_config["boot"] = "order=ide2;scsi0"

        add_log(f"Creating VM with config: {vm_config['name']}")

        # Create the VM
        proxmox.nodes(node).qemu.create(**vm_config)
        add_log(f"Nested Proxmox VM created with VMID {vmid}")

        state["nested_vmid"] = vmid

        # Start the VM if requested
        if config.get("start", True):
            add_log("Waiting for VM to be ready...")
            time.sleep(3)  # Give Proxmox time to finalize VM creation
            add_log("Starting nested Proxmox VM...")
            try:
                proxmox.nodes(node).qemu(vmid).status.start.post()
                add_log("Nested Proxmox VM started successfully")
                if answer_iso:
                    add_log(">>> SELECT 'Automated Installation' FROM BOOT MENU <<<")
                    add_log("The answer file will configure: DHCP network, ext4, root password='root'")
                    add_log("Installation takes ~5-10 minutes. VM will reboot when complete.")
            except Exception as start_err:
                add_log(f"Warning: Could not auto-start VM: {str(start_err)}")
                add_log("Please start the VM manually from Proxmox UI")

        state["status"] = "nested_created"
        add_log("Nested Proxmox creation complete!")

    except Exception as e:
        add_log(f"Error creating nested Proxmox: {str(e)}")
        state["status"] = "error"


@app.route("/api/create-nested", methods=["POST"])
def create_nested():
    """Create nested Proxmox hypervisor"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    if state["status"] not in ["idle", "nested_created", "vms_created", "error"]:
        return jsonify({"error": "Operation already in progress"}), 400

    config = request.json

    if not config.get("node"):
        return jsonify({"error": "Node is required"}), 400

    # Start background task
    thread = threading.Thread(target=create_nested_proxmox_task, args=(config,))
    thread.start()

    return jsonify({"status": "creating", "message": "Nested Proxmox creation started"})


def create_vms_task(config):
    """Background task to create VMs inside nested Proxmox"""
    try:
        state["status"] = "creating_vms"

        vm_count = config.get("count", 12)
        theme = config.get("theme")
        vm_names = generate_vm_names(vm_count, theme)

        add_log(f"Creating {vm_count} VMs with theme: {theme or 'random'}")

        # Connect to nested Proxmox
        nested_host = config.get("nested_host")
        nested_user = config.get("nested_user", "root@pam")
        nested_password = config.get("nested_password")

        if not all([nested_host, nested_password]):
            add_log("Error: Nested Proxmox credentials required")
            state["status"] = "error"
            return

        add_log(f"Connecting to nested Proxmox at {nested_host}...")

        nested_proxmox = ProxmoxAPI(
            nested_host,
            user=nested_user,
            password=nested_password,
            port=8006,
            verify_ssl=False
        )

        nodes = nested_proxmox.nodes.get()
        if not nodes:
            add_log("Error: No nodes found in nested Proxmox")
            state["status"] = "error"
            return

        node = nodes[0]["node"]
        add_log(f"Using node: {node}")

        created_vms = []
        base_vmid = 100

        for i, name in enumerate(vm_names):
            vmid = base_vmid + i
            add_log(f"Creating VM: {name} (VMID: {vmid})")

            try:
                # Create a minimal VM
                vm_config = {
                    "vmid": vmid,
                    "name": name,
                    "memory": config.get("vm_memory", 512),
                    "cores": config.get("vm_cores", 1),
                    "sockets": 1,
                    "net0": f"virtio,bridge={config.get('bridge', 'vmbr0')}",
                    "scsihw": "virtio-scsi-single",
                    "serial0": "socket",
                    "vga": "serial0",
                }

                # Add disk
                storage = config.get("storage", "local-lvm")
                vm_config["scsi0"] = f"{storage}:8"  # 8GB disk

                # Add cloud-init drive if available
                if config.get("use_cloudinit", True):
                    vm_config["ide2"] = f"{storage}:cloudinit"
                    vm_config["ciuser"] = "guest"
                    vm_config["cipassword"] = "guest"
                    vm_config["ipconfig0"] = "ip=dhcp"
                    vm_config["sshkeys"] = ""

                nested_proxmox.nodes(node).qemu.create(**vm_config)

                # Start the VM
                if config.get("start_vms", True):
                    nested_proxmox.nodes(node).qemu(vmid).status.start.post()

                created_vms.append({
                    "vmid": vmid,
                    "name": name,
                    "status": "running" if config.get("start_vms", True) else "stopped"
                })

                add_log(f"VM {name} created successfully")

            except Exception as e:
                add_log(f"Error creating VM {name}: {str(e)}")

        state["nested_vms"] = created_vms
        state["status"] = "vms_created"
        add_log(f"Created {len(created_vms)} VMs successfully!")

    except Exception as e:
        add_log(f"Error creating VMs: {str(e)}")
        state["status"] = "error"


@app.route("/api/create-vms", methods=["POST"])
def create_vms():
    """Create VMs inside nested Proxmox"""
    if state["status"] not in ["nested_created", "vms_created", "error"]:
        return jsonify({"error": "Nested Proxmox must be created first"}), 400

    config = request.json

    # Start background task
    thread = threading.Thread(target=create_vms_task, args=(config,))
    thread.start()

    return jsonify({"status": "creating", "message": "VM creation started"})


@app.route("/api/themes", methods=["GET"])
def get_themes():
    """Get available VM naming themes"""
    return jsonify({
        "themes": list(THEMES.keys()),
        "preview": {theme: THEMES[theme][:5] for theme in THEMES}
    })


def destroy_nested_task(config):
    """Background task to destroy nested Proxmox"""
    try:
        state["status"] = "destroying"
        proxmox = state["proxmox"]

        vmid = config.get("vmid") or state["nested_vmid"]
        node = config.get("node")

        if not vmid:
            add_log("Error: No nested Proxmox VMID specified")
            state["status"] = "error"
            return

        add_log(f"Destroying nested Proxmox VM {vmid}...")

        # Stop the VM first
        try:
            add_log("Stopping VM...")
            proxmox.nodes(node).qemu(vmid).status.stop.post()
            time.sleep(5)  # Wait for VM to stop
        except Exception as e:
            add_log(f"Stop failed (VM might already be stopped): {str(e)}")

        # Delete the VM
        add_log("Deleting VM...")
        proxmox.nodes(node).qemu(vmid).delete(purge=1)

        state["nested_vmid"] = None
        state["nested_vms"] = []
        state["status"] = "idle"
        add_log("Nested Proxmox destroyed successfully!")

    except Exception as e:
        add_log(f"Error destroying nested Proxmox: {str(e)}")
        state["status"] = "error"


@app.route("/api/destroy", methods=["POST"])
def destroy_nested():
    """Destroy nested Proxmox and all VMs"""
    if not state["connected"]:
        return jsonify({"error": "Not connected"}), 400

    config = request.json

    if not config.get("node"):
        return jsonify({"error": "Node is required"}), 400

    # Start background task
    thread = threading.Thread(target=destroy_nested_task, args=(config,))
    thread.start()

    return jsonify({"status": "destroying", "message": "Destruction started"})


@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Get operation logs"""
    return jsonify({"logs": state["logs"]})


@app.route("/api/logs", methods=["DELETE"])
def clear_logs():
    """Clear operation logs"""
    state["logs"] = []
    return jsonify({"status": "cleared"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
