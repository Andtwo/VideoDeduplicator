# 微信小程序下载后续接入

状态：待实施。本轮仅改造 Nginx 子路径代理。

用户已确认：达富星球小程序内已实现原生下载页 `/pages/common/media-download/index`，无需在本仓库开发原生页。

参考仓库： https://git.gzjunbo.net/liangjiongy/media-library.git
本地接入说明：`/Users/newbee/codex_workdir/media-library/docs/dafu-miniprogram-media-download-integration.md`。

后续工作：
- 引入微信 JSSDK，仅在 `window.__wxjs_environment === 'miniprogram'` 时桥接。
- 将处理结果下载地址转换为保留部署前缀的绝对同源 URL。
- 向原生页传入 `downloadUrl`、`mediaType=video`、`filename`。
- 保留普通浏览器下载及桥接不可用时的降级。
- 生产配置 HTTPS、WebView 业务域名和 downloadFile 合法域名。
- 在达富星球小程序真机验证下载和相册保存。
