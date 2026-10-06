# Persistent hosting on the NVIDIA network

Studio can run as a systemd user service on this workstation. It uses one editor process and one shared GPU stream. This is a private LAN/VPN deployment, not NVIDIA SSO or a public hosting service. A machine must have a route to the workstation; being signed in to a NVIDIA account alone does not provide that route.

## Prepare and review

Install the editor and optional renderer first with `./omni_setup/setup.sh runtime`. From the repository directory, generate a service configuration:

```bash
python3 deployment/install_user_service.py
```

The installer defaults to `127.0.0.1:8001` and writes these files without starting, stopping or reloading any service:

- `~/.config/systemd/user/blueprint-studio.service`
- `~/.config/blueprint-studio/host.env` (owner read/write only)

For the first installation, use `--host PRIVATE_IP --port 8001 --asset-root /path/to/OmniverseAssets` to bind the editor to a specific private interface. Use `--config-dir /tmp/studio-service-review` to stage files for review without installing them in systemd's configuration directory. Re-running the installer updates the unit but retains an existing environment file; edit that file explicitly when changing settings. The service uses the checkout and its virtual environment in place, so retain both at their installed paths.

For this workstation's internal pilot, retaining local access for tests as well as private-network access requires binding all interfaces:

```bash
python3 deployment/install_user_service.py --host 0.0.0.0 --port 8001 \
  --asset-root /localhome/local-mirfan/Repos/OmniverseAssets
```

This does not enforce NVIDIA identity or create a VPN. It relies on the host's private routing and the intended network access controls described below.

Check the generated unit:

```bash
systemd-analyze --user verify "$HOME/.config/systemd/user/blueprint-studio.service"
```

The environment sets `BLUEPRINT_STUDIO_ASSET_ROOT` explicitly. Optional `OVSTREAM_ICE_SERVERS` settings belong in the same private environment file; do not commit credentials. The generated service uses one Uvicorn worker because stream ownership is maintained in process memory. `Restart=on-failure` restarts the editor after a crash; stopping the service also terminates its renderer processes.

## Activate after reviewing access and existing processes

The current manually launched editor must release port 8001 before the service starts. Stop only that verified Studio process; port 8000 belongs to another application. Then run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now blueprint-studio.service
systemctl --user status blueprint-studio.service --no-pager
curl --fail http://127.0.0.1:8001/api/health
```

Use the configured private address instead of `127.0.0.1` in the health request if the service binds exclusively to that interface. To keep the user manager running after logout and start it at boot, enable lingering for this account:

```bash
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" -p Linger
```

`Linger=yes` and an enabled unit are both required for unattended startup. This keeps the editor available while the machine is powered on and awake. A restart does not automatically reopen the previous RTX scene; open the saved project and start its live view again. GPU streams remain on demand.

## Network and access limits

As inspected on 2026-10-06, this workstation's private interface is `10.46.71.211`, and its hostname is `smc521ge-0091.pdc1a2.colossus.nvidia.com`. Local hostname lookup resolves to `127.0.1.1`; this does not verify DNS resolution from another machine. The installed editor service is enabled with `Linger=yes` and listens on `0.0.0.0:8001`. A controlled service restart retained the saved project, and both loopback and `10.46.71.211` HTTP checks passed from the host. UFW remains inactive; no firewall or public routing changes were made. Access from another machine is still unverified. These observations can change.

| Purpose | Default transport and port |
| --- | --- |
| Editor and project API | TCP 8001 |
| RTX browser viewer | TCP 8088 |
| WebRTC signaling | TCP 49100 |
| WebRTC media | UDP 47998; the runtime can also negotiate dynamic UDP ports |

The editor bind setting does not restrict the renderer's listeners. The renderer currently binds its viewer and signaling listeners to all interfaces. Network restrictions must cover all of these paths, not just port 8001. Restrict routing/firewall access to the intended NVIDIA LAN/VPN clients; a private address alone is not an identity check. Do not add public port forwarding or a public tunnel. Routed VPN clients may need a suitable internal STUN/TURN service; a working editor page does not prove WebRTC connectivity.

Projects are stored under the checkout's `uploads/` and `output/` directories and are shared host data. The application has no user accounts, project ownership or per-user isolation. People with access to the service can operate the shared editor and stream; project URLs are not access-control credentials. One stream is shared across viewers, including camera movement. Authentication and network access controls must be assessed before widening the audience. The sample B1-1502 source documents and traces may contain personal information; review what is exposed to colleagues before sharing that example.

Verify from a second NVIDIA-network machine: open the editor, upload a non-sensitive test drawing, generate a scene, start the live view, and confirm moving video, camera controls and the selected resolution. Repeat from a VPN client if that is an intended access path. Until those checks pass, remote reachability remains unverified.

## Operations

```bash
systemctl --user restart blueprint-studio.service
journalctl --user -u blueprint-studio.service -n 100 --no-pager
systemctl --user stop blueprint-studio.service
systemctl --user disable blueprint-studio.service
```

An intentional stop does not trigger the crash restart policy. Restart after editing the environment file or updating code. Back up `uploads/` and `output/` separately from Git; also retain the external asset library referenced by scenes. System logs and project traces can contain local paths and project details, so inspect them before attaching them to [a feedback issue](https://github.com/irfanmsg/experiments/issues/new).

The editor and viewer expose their own `GET /api/runtime-trace` endpoints and **Libraries and APIs** panels. Use them to identify installed versions and successfully observed API actions; the two processes have different execution histories. These traces do not establish that a remote browser received frames. Reconstruction traces describe the source geometry and inferred design choices separately.
