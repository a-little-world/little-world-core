{
  description = "Little World Backend Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        # Setup script that initializes the development environment
        setupScript = pkgs.writeShellScriptBin "setup-dev" ''
          set -euo pipefail

          # Find project root by looking for docker-compose.yaml or .gitmodules
          # Start from current directory or dev/ directory
          if [ -f docker-compose.yaml ] || [ -f .gitmodules ]; then
            PROJECT_ROOT="$(pwd)"
          elif [ -f ../docker-compose.yaml ] || [ -f ../.gitmodules ]; then
            PROJECT_ROOT="$(cd .. && pwd)"
          else
            echo "❌ Error: Could not find project root (looking for docker-compose.yaml or .gitmodules)"
            exit 1
          fi
          
          cd "$PROJECT_ROOT"

          echo "🔧 Setting up development environment..."

          # 1. Initialize git submodules (idempotent)
          echo "📦 Initializing git submodules..."
          if [ -f .gitmodules ]; then
            # This command is idempotent - it won't fail if submodules are already initialized
            git submodule update --init --recursive
            echo "✅ Git submodules initialized"
          else
            echo "⚠️  No .gitmodules file found, skipping submodule initialization"
          fi

          # 2. Setup Python virtual environment (idempotent)
          echo "🐍 Setting up Python virtual environment..."
          if [ ! -d .venv ]; then
            ${pkgs.python3}/bin/python3 -m venv .venv
            echo "✅ Created Python virtual environment"
          else
            echo "✅ Python virtual environment already exists"
          fi

          # Activate venv and install requirements
          source .venv/bin/activate

          # Upgrade pip first
          pip install --upgrade pip --quiet

          # Install requirements (idempotent - pip handles this)
          if [ -f back/requirements.txt ]; then
            echo "📥 Installing back/requirements.txt..."
            pip install -r back/requirements.txt --quiet
            echo "✅ Installed back/requirements.txt"
          else
            echo "⚠️  back/requirements.txt not found"
          fi

          if [ -f back/requirements.dev.txt ]; then
            echo "📥 Installing back/requirements.dev.txt..."
            pip install -r back/requirements.dev.txt --quiet
            echo "✅ Installed back/requirements.dev.txt"
          else
            echo "⚠️  back/requirements.dev.txt not found"
          fi

          echo "✅ Python packages installed"

          # 3. Docker compose build (idempotent)
          echo "🐳 Building Docker images..."
          if command -v docker-compose &> /dev/null; then
            docker-compose build
          elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
            docker compose build
          else
            echo "⚠️  Docker Compose not found, skipping Docker build"
            exit 1
          fi

          echo "✅ Docker images built"
          echo ""
          echo "🎉 Development environment setup complete!"
        '';

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
            python3Packages.pip
            python3Packages.virtualenv
            git
            docker
            docker-compose
            setupScript
          ];

          shellHook = ''
            echo "🚀 Little World Backend Development Environment"
            echo ""
            echo "Available commands:"
            echo "  setup-dev  - Initialize submodules, setup Python venv, and build Docker images"
            echo ""
            echo "Run 'setup-dev' to set up the development environment."
          '';
        };

        packages.default = setupScript;
      });
}
