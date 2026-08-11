/**
 * PM2 · NewsC（API 仅本机 + Web 公网 8333）
 * 环境变量由 deploy 脚本 source /opt/newsc/.env 后注入。
 */
module.exports = {
  apps: [
    {
      name: "newsc-api",
      cwd: __dirname,
      script: "scripts/pm2-api.sh",
      interpreter: "bash",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      error_file: "logs/pm2-api-error.log",
      out_file: "logs/pm2-api-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true,
    },
    {
      name: "newsc-web",
      cwd: __dirname + "/apps/web",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 8333",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        NODE_ENV: "production",
        NODE_OPTIONS: "--max-old-space-size=512",
        PORT: 8333,
        ORCH_INTERNAL_URL: "http://127.0.0.1:8787",
      },
      error_file: "../../logs/pm2-web-error.log",
      out_file: "../../logs/pm2-web-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true,
    },
  ],
};
