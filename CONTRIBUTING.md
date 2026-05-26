# 贡献指南

感谢你有兴趣为 ShopEase Agent 做出贡献！🎉

## 如何贡献

### 1. Fork 并 Clone

```bash
# Fork 项目到你的账户
# Clone 你 Fork 的项目
git clone https://github.com/YOUR_USERNAME/shopease-agent.git
cd shopease-agent

# 添加上游仓库
git remote add upstream https://github.com/Wayne-git802/shopease-agent.git
```

### 2. 创建特性分支

```bash
# 从最新的 main/master 分支创建
git fetch upstream
git checkout -b feature/your-feature-name
```

### 3. 开发和测试

```bash
# 安装依赖
pip install -r requirements.txt

# 进行你的改动
# 确保代码通过测试
python -m pytest
```

### 4. 提交 PR

- 提交信息清晰，说明改动内容
- 在 PR 描述中关联相关的 Issue（如有）
- 确保所有测试通过
- 遵循代码规范

## 贡献类型

### 🐛 Bug 修复
- 先搜索是否有相关的 Issue
- 创建一个新的 Issue 描述 Bug
- 提交 PR 时链接该 Issue

### ✨ 新功能
- 先在 Issue 中讨论你的想法
- 等待维护者反馈
- 创建 PR 时参考讨论内容

### 📚 文档改进
- 改进 README、API 文档等
- 修复拼写错误和不清晰的地方

### 🔧 性能优化
- 提供基准测试数据
- 说明优化前后的性能对比

## 代码规范

- 使用有意义的变量名
- 添加必要的代码注释
- 保持代码风格一致
- 遵循 PEP 8（Python）规范

## 提交信息规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型包括：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档
- `style`: 代码格式（不改变逻辑）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 添加测试

例子：
```
feat(auth): add JWT token refresh mechanism

Implement automatic token refresh when access token expires.
Adds refresh token rotation for security.

Closes #123
```

## 问题反馈

- 使用 GitHub Issues 报告 Bug 或提出建议
- 提供清晰的描述和复现步骤
- 附加相关的错误日志或截图

## 行为准则

- 尊重他人
- 建设性的反馈
- 接受批评
- 专注于问题本身，而非个人

感谢你的贡献！ 💪