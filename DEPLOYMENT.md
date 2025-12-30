# Slop Deployment Operations Guide

This guide covers manual operations for verification, break-glass changes, and monitoring. Normal deployments are automated via CI/CD.

## Prerequisites

1. **Fly.io CLI**: Install the Fly CLI
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Authentication**: Log in to Fly.io
   ```bash
   fly auth login
   ```

## Verification Operations

### Verify Deployment Health

```bash
# Check overall application status
fly status

# Check machine health
fly machine list

# Verify health check endpoint
curl https://slop.fly.dev/health

# Check health check status
fly checks list
```

### Verify WebSocket Connectivity

```bash
# SSH into machine and check WebSocket server
fly ssh console
netstat -an | grep 8000
```

### Verify Database Connection

```bash
# Access SQLite database
fly ssh console
ls -la /data/
sqlite3 /data/slop.db ".tables"
```

### Verify Volume Mount

```bash
# Check persistent volume
fly volumes list

# Verify mount inside container
fly ssh console
df -h /data
ls -la /data/
```

## Monitoring

### Live Logs

```bash
# Stream live application logs
fly logs

# Filter for errors
fly logs | grep ERROR

# View specific number of recent logs
fly logs --tail 200
```

### Metrics Dashboard

Access web-based metrics:
- Application metrics: https://fly.io/apps/slop/monitoring
- Machine metrics: https://fly.io/apps/slop/machines

### Resource Usage

```bash
# Check machine resource usage
fly machine status

# View current scaling configuration
fly scale show
```

## Break-Glass Operations

### Emergency Restart

```bash
# Restart application (graceful)
fly apps restart slop

# Force restart machine (immediate)
fly machine restart <machine-id>
```

### Emergency Rollback

```bash
# List recent releases
fly releases

# Rollback to previous version
fly deploy --image <previous-image-sha>
```

### Scale Resources

```bash
# Increase memory (e.g., if OOM errors)
fly scale memory 2048

# Increase CPU
fly scale vm shared-cpu-2x

# Scale instances (e.g., if single instance fails)
fly scale count 2
```

### Update Secrets

```bash
# Rotate API keys
fly secrets set OPENAI_API_KEY=new-key-here
fly secrets set ANTHROPIC_API_KEY=new-key-here

# List configured secrets (values hidden)
fly secrets list
```

### Update Environment Variables

```bash
# Update CORS origins
fly secrets set CORS_ORIGINS=https://new-domain.com

# Verify environment variables
fly ssh console
env | grep CORS_ORIGINS
```

### Manual Deployment (Break-Glass Only)

```bash
# Deploy from local directory (bypasses CI/CD)
fly deploy --remote-only

# Deploy specific Docker image
fly deploy --image registry.fly.io/slop:specific-tag
```

### Database Recovery

```bash
# Create database backup
fly ssh console
sqlite3 /data/slop.db ".backup /data/backup_$(date +%Y%m%d_%H%M%S).db"
exit

# List volume snapshots
fly volumes snapshots list

# Create emergency snapshot
fly volumes snapshots create slop_data

# Restore from snapshot (requires volume recreation)
fly volumes create slop_data_new --snapshot-id <snapshot-id>
# Then update fly.toml mount source and redeploy
```

### SSH Access

```bash
# SSH into running machine
fly ssh console

# SSH to specific machine
fly ssh console --select

# Execute single command
fly ssh console -C "ps aux"
```

## Troubleshooting

### Health Checks Failing

```bash
# 1. Check logs for errors
fly logs --tail 100

# 2. Verify health endpoint locally in container
fly ssh console
curl http://localhost:8000/health

# 3. Check if app is running
ps aux | grep python
```

### Application Crashes

```bash
# 1. Check recent logs
fly logs --tail 500

# 2. Check machine status
fly machine list

# 3. Restart if necessary
fly apps restart slop
```

### Database Locked or Corrupted

```bash
# 1. SSH into machine
fly ssh console

# 2. Check database integrity
sqlite3 /data/slop.db "PRAGMA integrity_check;"

# 3. If corrupted, restore from snapshot
# See Database Recovery section above
```

### Out of Memory (OOM)

```bash
# 1. Check memory usage
fly ssh console
free -h

# 2. Scale memory immediately
fly scale memory 2048

# 3. Monitor after scaling
fly logs
```

### WebSocket Connection Issues

```bash
# 1. Verify auto_stop_machines is false
fly config show | grep auto_stop_machines

# 2. Check WebSocket connections
fly ssh console
netstat -an | grep ESTABLISHED | grep 8000

# 3. Verify proxy settings
fly logs | grep websocket
```

### Volume Full

```bash
# 1. Check volume usage
fly ssh console
df -h /data

# 2. Clean up old data if needed
# (Application-specific cleanup)

# 3. Expand volume if necessary
fly volumes extend <volume-id> --size 5
```

## Regular Maintenance

### Log Rotation

Fly.io automatically rotates logs. Access historical logs via dashboard:
- https://fly.io/apps/slop/monitoring

### Security Updates

Monitor for:
- Python base image updates (automated via CI/CD)
- Dependency updates (automated via Dependabot/Renovate)
- Fly.io platform updates (announced in Fly.io status page)

### Cost Monitoring

```bash
# View billing dashboard
fly dashboard billing

# Check current resource allocation
fly scale show
```

## Emergency Contacts

- **Fly.io Status**: https://status.fly.io/
- **Fly.io Community**: https://community.fly.io/
- **Fly.io Support**: support@fly.io (for paid plans)

## Common Alert Responses

### Alert: Health Check Failed
1. Check logs: `fly logs --tail 100`
2. Verify app is running: `fly ssh console -C "ps aux"`
3. Restart if needed: `fly apps restart slop`

### Alert: High Memory Usage
1. Check current usage: `fly ssh console -C "free -h"`
2. Scale memory: `fly scale memory 2048`
3. Investigate memory leak in logs

### Alert: High Error Rate
1. Stream logs: `fly logs | grep ERROR`
2. Check recent deployments: `fly releases`
3. Rollback if needed: Deploy previous image

### Alert: WebSocket Disconnections
1. Verify machines running: `fly machine list`
2. Check auto_stop setting: `fly config show`
3. Restart machines: `fly apps restart slop`

## Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Fly.io Status Page](https://status.fly.io/)
- [WebSocket Support](https://fly.io/docs/networking/websockets/)
- [Persistent Volumes](https://fly.io/docs/volumes/)
