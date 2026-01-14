# DummyProx

A containerized web interface for creating nested Proxmox hypervisors with auto-provisioned VMs.

## Features

- **Web Interface** - Simple, modern UI with Proxmox connection sidebar
- **Nested Proxmox Creation** - Automatically create a Proxmox hypervisor VM on your existing Proxmox server
- **VM Provisioning** - Deploy 10-15 lightweight VMs inside the nested Proxmox
- **Themed VM Names** - Random themed names (databases, planets, animals, elements, greek gods)
- **SSH Access** - All VMs come with `guest/guest` credentials for easy SSH access
- **Easy Cleanup** - One-click destruction of the entire nested setup

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-repo/DummyProx.git
cd DummyProx

# Build and run
docker-compose up -d

# Access the web interface
open http://localhost:8080
```

### Using Docker

```bash
# Build the image
docker build -t dummyprox .

# Run the container
docker run -d -p 8080:80 --name dummyprox dummyprox

# Access the web interface
open http://localhost:8080
```

## Usage

1. **Connect to Proxmox**
   - Enter your Proxmox server details in the sidebar (host, port, username, password)
   - Click "Connect" to establish the connection
   - Select the target node from the dropdown

2. **Create Nested Proxmox**
   - Configure the nested Proxmox VM settings (name, memory, cores, disk)
   - Select the storage location
   - Click "Create Nested Proxmox"
   - Wait for the VM to be created and started

3. **Provision VMs**
   - Once the nested Proxmox is running, get its IP address
   - Enter the nested Proxmox IP and root password
   - Select the number of VMs (10-15) and naming theme
   - Click "Create VMs"

4. **Access VMs**
   - SSH into any VM using: `ssh guest@<vm-ip>`
   - Password: `guest`

5. **Cleanup**
   - Click "Destroy Everything" to remove the nested Proxmox and all VMs

## VM Naming Themes

| Theme | Example Names |
|-------|--------------|
| Databases | mongo-01, postgres-02, mysql-03 |
| Planets | mercury-01, venus-02, earth-03 |
| Animals | lion-01, tiger-02, bear-03 |
| Elements | hydrogen-01, helium-02, lithium-03 |
| Greek | zeus-01, hera-02, apollo-03 |

## Requirements

- Docker and Docker Compose
- Proxmox VE server with API access
- Nested virtualization enabled on the host

### Enabling Nested Virtualization

On your Proxmox host, ensure nested virtualization is enabled:

```bash
# Check if nested virtualization is enabled
cat /sys/module/kvm_intel/parameters/nested  # Intel
cat /sys/module/kvm_amd/parameters/nested    # AMD

# Enable if not already (add to /etc/modprobe.d/kvm.conf)
options kvm_intel nested=1  # Intel
options kvm_amd nested=1    # AMD
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/connect` | POST | Connect to Proxmox |
| `/api/disconnect` | POST | Disconnect from Proxmox |
| `/api/status` | GET | Get current status |
| `/api/nodes` | GET | List available nodes |
| `/api/storage` | GET | List storage options |
| `/api/themes` | GET | List VM naming themes |
| `/api/create-nested` | POST | Create nested Proxmox |
| `/api/create-vms` | POST | Create VMs in nested Proxmox |
| `/api/destroy` | POST | Destroy nested setup |
| `/api/logs` | GET/DELETE | View/clear logs |

## Architecture

```
DummyProx/
├── backend/
│   ├── app.py              # Flask API server
│   └── requirements.txt    # Python dependencies
├── frontend/
│   └── index.html          # Web interface
├── Dockerfile              # Multi-stage Docker build
├── docker-compose.yml      # Docker Compose config
├── nginx.conf              # Nginx reverse proxy config
└── supervisord.conf        # Process manager config
```

## Development

### Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
python app.py

# Frontend (serve with any static server)
cd frontend
python -m http.server 8000
```

## License

MIT
