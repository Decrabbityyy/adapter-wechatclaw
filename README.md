# nonebot-adapter-wechatclaw

通过 微信ClawBot 连接微信

### 登录
运行命令扫码获得 WECHATCLAW_TOKEN 和 WECHATCLAW_ACCOUNT_ID


*需安装 nonebot-adapter-wechatclaw[login]*
``` shell
nb wechatclaw-login
```
或者 环境内运行
```
wechatclaw-login
```

### Driver

参考 [driver](https://nonebot.dev/docs/appendices/config#driver) 配置项，添加 `HTTPClient` 支持。

如：

```dotenv
DRIVER=~httpx
```