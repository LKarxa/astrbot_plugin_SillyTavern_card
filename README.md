# astrbot_plugin_SillyTavern_card

一个将 SillyTavern 角色卡（PNG 格式）转换为 Lorebook YAML 与角色信息的插件。

需要安装lorebook插件[https://github.com/Raven95676/astrbot_plugin_lorebook_lite](https://github.com/Raven95676/astrbot_plugin_lorebook_lite)

此插件可以从 PNG 图像的元数据中提取角色信息，并将其处理为两种形式：
1. 结构化的文本信息 - 包含角色的基本属性（name, prompt, first_mes）
2. Lorebook 格式的 YAML 文件 - 用于 astrbot_plugin_lorebook_lite 插件

## 功能特性

- **自动提取角色卡信息** - 从 SillyTavern PNG 角色卡中读取元数据
- **格式化角色基本信息** - 提取并格式化角色名称、描述和开场白
- **生成 Lorebook YAML** - 将角色卡中的条目转换为标准 Lorebook YAML 格式
- **命令行支持** - 提供简单的命令进行文件转换和管理
- **双引号转义处理** - 确保所有文本值都被正确引用和转义

## 目录结构

插件安装后将创建以下目录结构：

```
astrbot_plugin_SillyTavern_card/
├── main.py              # 主入口文件
├── character_card_parser.py  # PNG 解析模块
├── json_to_lorebook_yaml.py  # YAML 转换模块
├── card/                # 存放角色卡 PNG 文件
└── requirements.txt     # 依赖列表

data/
├── lorebooks/           # 存放生成的 YAML 文件
└── characters/          # 角色信息的相关目录
```

## 安装与配置

1. 将插件目录放入 Astrbot 的插件目录中（通常为 `plugins/`）
2. 确保安装了必要依赖：`pypng`
3. 重启 Astrbot 或加载插件
4. 将 SillyTavern 角色卡 PNG 文件放入 `card/` 目录中

## 使用方法

### 列出可用的角色卡

```
/list_cards
```

显示 `card/` 目录中所有可用的 PNG 角色卡文件。

### 转换角色卡

```
/convert_card [文件名]
```

例如：
```
/convert_card alice.png
```
或简写为：
```
/convert_card alice
```

执行后，插件将：
1. 从 PNG 文件提取角色数据
2. 显示角色基本信息（name、prompt、first_mes）
3. 生成 Lorebook YAML 文件并保存到 `data/lorebooks/` 目录

### 查看帮助信息

```
/help_convert
```

显示插件的详细使用说明。

## 字段映射

插件处理的主要字段映射关系：

| 角色卡字段 | 输出字段 | 说明 |
|------------|----------|------|
| name | name | 角色名称 |
| description | prompt | 角色描述 |
| begin_dialogs/first_mes/greeting 等 | first_mes | 角色开场白 |


## 注意事项

1. PNG 文件必须包含有效的角色卡元数据，通常由 SillyTavern 生成
2. 转换后的 YAML 文件与原 PNG 文件同名（但扩展名不同）
3. 确保 `data/lorebooks/` 目录有写入权限

## 常见问题

**Q: 为什么提示找不到 PNG 文件？**  
A: 确保 PNG 文件放在了插件的 `card/` 目录中。

**Q: 转换后的 YAML 文件在哪里？**  
A: 在 `data/lorebooks/` 目录中，与原 PNG 文件同名。

**Q: 为什么一些角色卡信息不完整？**  
A: 不同的角色卡可能使用不同的字段格式，插件尝试支持多种格式，但无法保证完全兼容所有变体。

## 贡献

欢迎通过以下方式贡献：
- 提交 bug 报告
- 提出功能建议
- 提交代码改进

项目地址: [https://github.com/LKarxa/astrbot_plugin_SillyTavern_card](https://github.com/LKarxa/astrbot_plugin_SillyTavern_card)