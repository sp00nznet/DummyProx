<p align="center">
  <img src="https://img.shields.io/badge/Proxmox-Nested-E57000?style=for-the-badge&logo=proxmox&logoColor=white" alt="Proxmox"/>
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/Python-Flask-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
</p>

<h1 align="center">DummyProx</h1>

<p align="center">
  <strong>Spin up nested Proxmox environments with auto-provisioned VMs in minutes</strong>
</p>

<p align="center">
  A containerized web interface for creating nested Proxmox hypervisors with automatically deployed, SSH-ready virtual machines. Perfect for testing, training labs, and development environments.
</p>

---

## What is DummyProx?

DummyProx lets you create a **Proxmox hypervisor inside your existing Proxmox server** (nested virtualization), then automatically populates it with 10-15 lightweight VMs. Each VM comes pre-configured with SSH access using `guest/guest` credentials.

Think of it as a "lab in a box" - spin up an entire virtualized infrastructure for testing, tear it down when you're done, and start fresh whenever you need.

---

## Features

| Feature | Description |
|---------|-------------|
| **One-Click Nested Proxmox** | Deploy a fully functional Proxmox hypervisor as a VM |
| **Auto VM Provisioning** | Automatically create 10-15 VMs with a single click |
| **Server-Themed Names** | VMs get realistic names like `mongo-01`, `nginx-02`, `kafka-03` |
| **SSH Ready** | All VMs accessible via `ssh guest@<ip>` with password `guest` |
| **Easy Cleanup** | Destroy the entire nested environment with one button |
| **Real-Time Logs** | Watch operations happen live in the web interface |
| **Dockerized** | Runs anywhere Docker runs |

---

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/your-repo/DummyProx.git
cd DummyProx
docker-compose up -d
```

Open **http://localhost:8080** in your browser.

### Option 2: Docker

```bash
docker build -t dummyprox .
docker run -d -p 8080:80 --name dummyprox dummyprox
```

---

## How to Use

### Step 1: Connect to Your Proxmox Server

Enter your Proxmox server details in the sidebar:
- **Host**: IP address or hostname of your Proxmox server
- **Port**: API port (default: 8006)
- **Username**: e.g., `root@pam`
- **Password**: Your Proxmox password

### Step 2: Create the Nested Proxmox

Configure your nested hypervisor:
- **Name**: Give it a name (default: `nested-proxmox`)
- **Memory**: RAM allocation (recommended: 16GB+)
- **Cores**: CPU cores (recommended: 4+)
- **Disk**: Storage size (recommended: 100GB+)

Click **Create Nested Proxmox** and wait for it to boot.

### Step 3: Provision the VMs

Once your nested Proxmox is running:
1. Get its IP address from the Proxmox console
2. Enter the IP and root password in the "Provision VMs" section
3. Choose how many VMs (10-15) and pick a naming theme
4. Click **Create VMs**

### Step 4: Access Your VMs

SSH into any VM:
```bash
ssh guest@<vm-ip>
# Password: guest
```

### Step 5: Cleanup

When you're done, click **Destroy Everything** to remove the nested Proxmox and all VMs inside it.

---

## VM Naming Themes

VMs are named after real server applications to create a realistic lab environment:

| Theme | Example Names |
|-------|---------------|
| **Databases** | `mongo-01`, `postgres-02`, `redis-03`, `elastic-04`, `cassandra-05` |
| **Web Servers** | `nginx-01`, `apache-02`, `caddy-03`, `traefik-04`, `haproxy-05` |
| **Messaging** | `kafka-01`, `rabbit-02`, `nats-03`, `pulsar-04`, `zeromq-05` |
| **Monitoring** | `prometheus-01`, `grafana-02`, `datadog-03`, `nagios-04`, `zabbix-05` |
| **Containers** | `docker-01`, `podman-02`, `kubernetes-03`, `nomad-04`, `swarm-05` |

---

## Project Structure

```
DummyProx/
├── backend/
│   ├── app.py                 # Flask API server
│   └── requirements.txt       # Python dependencies
├── frontend/
│   └── index.html             # Web UI (single-page app)
├── Dockerfile                 # Multi-stage container build
├── docker-compose.yml         # Easy deployment config
├── nginx.conf                 # Reverse proxy setup
├── supervisord.conf           # Process manager
├── .gitignore
└── .dockerignore
```

---

## What's Under the Hood

### Backend (Python/Flask)
- **Proxmox API Integration**: Uses `proxmoxer` library to communicate with Proxmox
- **Async Operations**: Background threads handle long-running tasks
- **Real-Time Logging**: All operations logged with timestamps
- **RESTful API**: Clean endpoints for all operations

### Frontend (HTML/CSS/JS)
- **Modern Dark UI**: Clean, responsive interface
- **Connection Sidebar**: Always-visible Proxmox connection panel
- **Live Updates**: Polls for status changes every 2 seconds
- **No Dependencies**: Pure vanilla JavaScript, no frameworks

### Infrastructure
- **Nginx**: Serves frontend and proxies API requests
- **Supervisor**: Manages backend and nginx processes
- **Docker**: Single container runs everything

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/connect` | POST | Connect to Proxmox server |
| `/api/disconnect` | POST | Disconnect from Proxmox |
| `/api/status` | GET | Get current operation status |
| `/api/nodes` | GET | List available Proxmox nodes |
| `/api/storage` | GET | List storage options for a node |
| `/api/themes` | GET | List available VM naming themes |
| `/api/create-nested` | POST | Create nested Proxmox hypervisor |
| `/api/create-vms` | POST | Create VMs in nested Proxmox |
| `/api/destroy` | POST | Destroy nested Proxmox and VMs |
| `/api/logs` | GET | Get operation logs |
| `/api/logs` | DELETE | Clear operation logs |

---

## Requirements

### Host Requirements
- **Proxmox VE** 7.0+ with API access enabled
- **Nested Virtualization** enabled on the host

### Enabling Nested Virtualization

Check if it's already enabled:
```bash
# Intel CPUs
cat /sys/module/kvm_intel/parameters/nested

# AMD CPUs
cat /sys/module/kvm_amd/parameters/nested
```

If not enabled, add to `/etc/modprobe.d/kvm.conf`:
```bash
# Intel
options kvm_intel nested=1

# AMD
options kvm_amd nested=1
```

Then reload the module or reboot.

---

## Development

Run locally without Docker:

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
python app.py

# Terminal 2: Frontend
cd frontend
python -m http.server 8000
```

Backend runs on `http://localhost:5000`, frontend on `http://localhost:8000`.

---

## License

MIT License - do whatever you want with it.
