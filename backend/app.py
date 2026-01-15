"""
DummyProx - Nested Proxmox Hypervisor Manager
Flask backend for managing nested Proxmox deployments
"""

import os
import random
import time
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS
from proxmoxer import ProxmoxAPI
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
            "name": config.get("name", "nested-proxmox"),
            "memory": config.get("memory", 16384),
            "cores": config.get("cores", 4),
            "sockets": 1,
            "cpu": "host",
            "net0": f"virtio,bridge={config.get('bridge', 'vmbr0')}",
            "scsihw": "virtio-scsi-single",
            "boot": "order=scsi0;ide2",
            "agent": "enabled=1",
        }

        # Add disk - strip 'G' suffix as Proxmox expects just the number for LVM
        # Use 'or' to handle empty string from frontend
        storage = config.get("storage") or "local-lvm"
        disk_size = (config.get("disk_size") or "100G").rstrip("Gg")
        vm_config["scsi0"] = f"{storage}:{disk_size}"

        # Add cloud-init for guest/guest credentials
        vm_config["ide2"] = f"{storage}:cloudinit"
        vm_config["ciuser"] = "guest"
        vm_config["cipassword"] = "guest"
        vm_config["ipconfig0"] = "ip=dhcp"

        # Add ISO if provided (uses ide3 since ide2 is cloud-init)
        if config.get("iso"):
            vm_config["ide3"] = f"{config['iso']},media=cdrom"
            vm_config["boot"] = "order=ide3;scsi0"  # Boot from ISO first

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
