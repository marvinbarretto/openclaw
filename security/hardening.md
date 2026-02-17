# VPS Hardening Checklist

## SSH

- [ ] Disable password authentication (use SSH keys only)
- [ ] Change default SSH port (optional, security-through-obscurity)
- [ ] Restrict SSH access to known IPs (via UFW or Cloudflare Access)

## Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 443/tcp
sudo ufw enable
```

## Fail2Ban

- [ ] Install: `sudo apt install fail2ban`
- [ ] Configure SSH jail
- [ ] Monitor logs: `sudo fail2ban-client status sshd`

## Automatic Updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Cloudflare Proxy

- [ ] Only allow traffic from Cloudflare IPs to port 443
- [ ] Use Cloudflare Access for admin endpoints (if any)

## Skill Vetting

- [ ] Review source code of each OpenClaw skill before enabling
- [ ] Check skills don't exfiltrate data or run arbitrary commands
- [ ] Pin skill versions, don't auto-update without review

## Data Privacy

- [ ] Understand what Telegram messages are stored and where
- [ ] Encrypt data at rest if storing conversation history
- [ ] Set up log rotation to avoid unbounded disk usage
