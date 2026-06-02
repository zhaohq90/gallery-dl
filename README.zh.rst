==========
gallery-dl
==========

*gallery-dl* 是一个命令行程序，
用于从多个图片托管网站下载图片画廊和集合
（详见 `支持的站点 <docs/supportedsites.md>`__）。
它是一个跨平台工具，
提供丰富的
`命令行选项 <https://gdl-org.github.io/docs/options.html>`__ 和
`配置选项 <https://gdl-org.github.io/docs/configuration.html>`__，
以及强大的
`文件命名功能 <https://gdl-org.github.io/docs/formatting.html>`__。

-----

项目迁移
========

| 活跃开发已迁移至 `Codeberg <https://codeberg.org/mikf/gallery-dl>`__
| （详见 `[公告] 迁移至 Codeberg <https://github.com/mikf/gallery-dl/issues/9374>`__）

-----


.. contents::

|pypi| |discord| |build|


依赖
====

- Python_ 3.8+
- Requests_

可选依赖
--------

- yt-dlp_ 或 youtube-dl_：HLS/DASH 视频下载、``ytdl`` 集成
- FFmpeg_：Pixiv Ugoira 转换
- mkvmerge_：精确的 Ugoira 帧时间码
- PySocks_：SOCKS 代理支持
- brotli_ 或 brotlicffi_：Brotli 压缩支持
- zstandard_：Zstandard 压缩支持
- PyYAML_：YAML 配置文件支持
- toml_：TOML 配置文件支持（Python<3.11）
- SecretStorage_：GNOME 密钥环密码，用于 ``--cookies-from-browser``
- Psycopg_：PostgreSQL 归档支持
- truststore_：原生系统证书支持
- Jinja_：Jinja 模板支持


安装
====


Pip
---

*gallery-dl* 的稳定版本发布在 PyPI_ 上，
可以使用 pip_ 轻松安装或升级：

.. code:: bash

    python -m pip install -U gallery-dl

直接安装 ``master`` 分支的最新开发版本
也可以通过 pip_ 完成：

.. code:: bash

    python -m pip install -U --force-reinstall --no-deps https://codeberg.org/mikf/gallery-dl/archive/master.tar.gz

如果尚未安装 Requests_，请省略 :code:`--no-deps`。

注意：Windows 用户应使用 :code:`py` 替代 :code:`python`。

建议使用最新版本的 pip_，
包括必需的包 :code:`setuptools` 和 :code:`wheel`。
为确保这些包是最新的，请运行：

.. code:: bash

    python -m pip install --upgrade pip setuptools wheel


独立可执行文件
--------------

包含 Python 解释器和所需 Python 包的预构建可执行文件
可用于：

- `Windows <https://codeberg.org/mikf/gallery-dl/releases/download/v1.32.1/gallery-dl.exe>`__
  （需要 `Microsoft Visual C++ Redistributable Package (x86) <https://aka.ms/vs/17/release/vc_redist.x86.exe>`__）
- `Linux   <https://codeberg.org/mikf/gallery-dl/releases/download/v1.32.1/gallery-dl.bin>`__


每夜构建版
----------

| 从最新提交构建的可执行文件可在以下地址找到
| https://github.com/gdl-org/builds/releases


Snap
----

使用支持 Snapd_ 的发行版的 Linux 用户可以从 Snap Store 安装 *gallery-dl*：

.. code:: bash

    snap install gallery-dl


Chocolatey
----------

已安装 Chocolatey_ 的 Windows 用户可以从 Chocolatey Community Packages 仓库安装 *gallery-dl*：

.. code:: powershell

    choco install gallery-dl


Scoop
-----

*gallery-dl* 也可通过 Scoop_ 的 "main" bucket 供 Windows 用户使用：

.. code:: powershell

    scoop install gallery-dl


Homebrew
--------

对于使用 Homebrew 的 macOS 或 Linux 用户：

.. code:: bash

    brew install gallery-dl


MacPorts
--------

对于使用 MacPorts 的 macOS 用户：

.. code:: bash

    sudo port install gallery-dl


Docker
------

使用仓库中的 Dockerfile：

.. code:: bash

    git clone https://codeberg.org/mikf/gallery-dl.git
    cd gallery-dl/
    docker build -t gallery-dl:latest .

从 `Docker Hub <https://hub.docker.com/r/mikf123/gallery-dl>`__ 拉取镜像：

.. code:: bash

    docker pull mikf123/gallery-dl
    docker tag mikf123/gallery-dl gallery-dl

从 `GitHub Container Registry <https://github.com/mikf/gallery-dl/pkgs/container/gallery-dl>`__ 拉取镜像：

.. code:: bash

    docker pull ghcr.io/mikf/gallery-dl
    docker tag ghcr.io/mikf/gallery-dl gallery-dl

使用 ``dev`` 标签拉取从最新提交构建的 *每夜构建版* 镜像：

.. code:: bash

    docker pull mikf123/gallery-dl:dev
    docker pull ghcr.io/mikf/gallery-dl:dev

要运行容器，您可能需要挂载宿主机上的一些目录，以便配置文件和下载内容在多次运行之间持久化。

请确保下载仓库中的示例配置文件并将其放在挂载的卷位置，或在那里创建一个空文件。

如果您给容器使用了不同的标签或正在使用 podman，请相应调整。如果不确定名称，请运行 ``docker image ls`` 检查。

这将在每次使用后删除容器，因此您始终拥有一个全新的运行环境。如果您设置了 CI/CD 流水线来自动构建容器，也可以添加 ``--pull=newer`` 标志，以便在运行时 docker 检查是否有更新的容器并在运行前下载。

.. code:: bash

    docker run --rm  -v $HOME/Downloads/:/gallery-dl/ -v $HOME/.config/gallery-dl/gallery-dl.conf:/etc/gallery-dl.conf -it gallery-dl:latest

您也可以为 shell 添加 "gallery-dl" 别名，或创建一个简单的 bash 脚本放在 $PATH 中作为此命令的垫片。


Nix 和 Home Manager
-------------------

将 *gallery-dl* 添加到系统环境：

.. code:: nix

    environment.systemPackages = with pkgs; [
      gallery-dl
    ];

使用 :code:`nix-shell`：

.. code:: bash

    nix-shell -p gallery-dl

.. code:: bash

    nix-shell -p gallery-dl --run "gallery-dl <args>"

对于 Home Manager 用户，可以声明式管理 *gallery-dl*：

.. code:: nix

    programs.gallery-dl = {
      enable = true;
      settings = {
        extractor.base-directory = "~/Downloads";
      };
    };

或者，如果不想声明式管理，只需将其添加到 :code:`home.packages`：

.. code:: nix

    home.packages = with pkgs; [
      gallery-dl
    ];

完成这些更改后，只需重新构建配置并打开新 shell 即可使用 *gallery-dl*。


使用
====

要使用 *gallery-dl*，只需使用您想要下载图片的 URL 调用它：

.. code:: bash

    gallery-dl [OPTIONS]... URLS...

使用 :code:`gallery-dl --help` 或查看 `<docs/options.md>`__
获取所有命令行选项的完整列表。


示例
----

下载图片；以下是通过标签搜索 'bonocho' 从 danbooru 下载：

.. code:: bash

    gallery-dl "https://danbooru.donmai.us/posts?tags=bonocho"


获取来自支持身份验证的网站的图片直链，使用用户名和密码：

.. code:: bash

    gallery-dl -g -u "<username>" -p "<password>" "https://twitter.com/i/web/status/604341487988576256"


按章节号和语言过滤漫画章节：

.. code:: bash

    gallery-dl --chapter-filter "10 <= chapter < 20" -o "lang=fr" "https://mangadex.org/title/59793dd0-a2d8-41a2-9758-8197287a8539"


| 搜索远程资源中的 URL 并从中下载图片：
| （无法找到对应提取器的 URL 将被静默忽略）

.. code:: bash

    gallery-dl "r:https://pastebin.com/raw/FLwrCYsT"


如果某个网站的地址对其提取器来说是非标准的，您可以在 URL 前加上
提取器名称以强制使用特定提取器：

.. code:: bash

    gallery-dl "tumblr:https://sometumblrblog.example"


配置
====

*gallery-dl* 的配置文件使用基于 JSON 的文件格式。


文档
----

所有可用配置选项及其说明的列表
可在 `<https://gdl-org.github.io/docs/configuration.html>`__ 找到。

| 包含所有选项默认值的默认配置文件，
  请参见 `<docs/gallery-dl.conf>`__。

| 包含更复杂设置和选项用法的注释示例，
  请参见 `<docs/gallery-dl-example.conf>`__。


配置位置
--------

*gallery-dl* 在以下位置搜索配置文件：

Windows：
    * ``%APPDATA%\gallery-dl\config.json``
    * ``%USERPROFILE%\gallery-dl\config.json``
    * ``%USERPROFILE%\gallery-dl.conf``

    （``%USERPROFILE%`` 通常指用户的主目录，
    即 ``C:\Users\<username>\``）

Linux、macOS 等：
    * ``/etc/gallery-dl.conf``
    * ``${XDG_CONFIG_HOME}/gallery-dl/config.json``
    * ``${HOME}/.config/gallery-dl/config.json``
    * ``${HOME}/.gallery-dl.conf``

当作为 `可执行文件 <独立可执行文件_>`__ 运行时，
*gallery-dl* 还会在可执行文件所在目录中查找 ``gallery-dl.conf`` 文件。

可以同时使用多个配置文件。
在这种情况下，第一个之后的文件中的任何值都将合并到已加载的设置中，
并可能覆盖之前的值。


认证
====

用户名和密码
------------

某些提取器要求您提供有效的登录凭据（用户名和密码对）。
这对于以下站点是必需的：
``nijie``，
以及以下站点是可选的：
``aryion``、
``danbooru``、
``e621``、
``idolcomplex``、
``imgbb``、
``inkbunny``、
``mangadex``、
``mangoxo``、
``pillowfort``、
``sankaku``、
``subscribestar``、
``tapas``、
``tsumino``
和 ``zerochan``。

您可以在 `配置文件 <#配置>`__ 中设置所需信息：

.. code:: json

    {
        "extractor": {
            "subscribestar": {
                "username": "<username>",
                "password": "<password>"
            }
        }
    }

或通过 :code:`-u/--username` 和 :code:`-p/--password` 命令行选项，
或通过 :code:`-o/--option` 命令行选项直接提供：

.. code:: bash

    gallery-dl -u "<username>" -p "<password>" "URL"
    gallery-dl -o "username=<username>" -o "password=<password>" "URL"


Cookies
-------

对于因 CAPTCHA 或类似原因无法使用用户名和密码登录，
或尚未实现该功能的站点，您可以使用
浏览器登录会话中的 cookies 并将其输入 *gallery-dl*。

可以通过配置文件中的
`cookies <https://gdl-org.github.io/docs/configuration.html#extractor-cookies>`__
选项实现，指定以下内容：

- | 浏览器插件导出的 Mozilla/Netscape 格式 cookies.txt 文件的路径
  | （例如 Chrome 的 `Get cookies.txt LOCALLY <https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>`__、
    Firefox 的 `Export Cookies <https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/>`__）

- | 从浏览器开发者工具收集的名称-值对列表
  | （`Chrome <https://developers.google.com/web/tools/chrome-devtools/storage/cookies>`__、
     `Firefox <https://developer.mozilla.org/en-US/docs/Tools/Storage_Inspector>`__）

- | 要从中提取 cookies 的浏览器名称
  | （支持的浏览器包括基于 Chromium 的浏览器、Firefox 和 Safari）

例如：

.. code:: json

    {
        "extractor": {
            "instagram": {
                "cookies": "$HOME/path/to/cookies.txt"
            },
            "patreon": {
                "cookies": {
                    "session_id": "K1T57EKu19TR49C51CDjOJoXNQLF7VbdVOiBrC9ye0a"
                }
            },
            "twitter": {
                "cookies": ["firefox"]
            }
        }
    }

| 您也可以使用 :code:`--cookies` 命令行选项指定 cookies.txt 文件，
| 或使用 :code:`--cookies-from-browser` 指定要从中提取 cookies 的浏览器：

.. code:: bash

    gallery-dl --cookies "$HOME/path/to/cookies.txt" "URL"
    gallery-dl --cookies-from-browser firefox "URL"


OAuth
-----

*gallery-dl* 支持通过 OAuth_ 对某些提取器进行用户认证。
这对于以下站点是必需的：
``pixiv``，
以及以下站点是可选的：
``deviantart``、
``flickr``、
``reddit``、
``smugmug``、
``tumblr``
和 ``mastodon`` 实例。

将您的账户链接到 *gallery-dl* 会授予其代表您的账户发起请求的能力，
使其能够访问公开用户无法获取的资源。

要开始，请使用 ``oauth:<站点名称>`` 作为参数调用它。
例如：

.. code:: bash

    gallery-dl oauth:flickr

您将被引导至站点的授权页面，并要求授予
*gallery-dl* 读取权限。授权后，您将看到一个或多个
"令牌"，这些应添加到您的配置文件中。

要认证 ``mastodon`` 实例，请使用
``oauth:mastodon:<实例>`` 作为参数运行 *gallery-dl*。例如：

.. code:: bash

    gallery-dl oauth:mastodon:pawoo.net
    gallery-dl oauth:mastodon:https://mastodon.social/


为什么使用 RST 格式？
=====================

*gallery-dl* 使用 **reStructuredText (RST)** 格式而非 Markdown 来编写
README 和文档，主要原因如下：

1. **PyPI 原生支持**
   RST 是 Python Package Index (PyPI_) 原生支持的标记语言。
   当用户在 PyPI 上查看 *gallery-dl* 的包页面时，RST 格式的 README
   可以直接被渲染为格式化的 HTML，无需额外转换。这是 Python 生态系统中
   约定俗成的做法。

2. **Sphinx 文档兼容**
   RST 是 Sphinx_（Python 官方文档生成工具）的原生格式。
   *gallery-dl* 的在线文档（托管在 https://gdl-org.github.io/docs/）
   使用 Sphinx 构建，使用 RST 格式可以保持 README 和文档之间的一致性。

3. **更强大的结构化指令**
   RST 提供了丰富的指令（directives）来组织内容：
   ``.. code::`` 用于代码块（支持语法高亮）、
   ``.. contents::`` 自动生成目录、
   以及灵活的交叉引用和脚注系统。
   这些在 Markdown 中要么不支持，要么需要非标准扩展。

4. **链接目标管理**
   RST 允许在文件末尾集中定义链接目标（如 ``.. _Python: https://...``），
   使正文保持整洁，避免 Markdown 中内联链接打断阅读体验的问题。

总而言之，对于 Python 项目，RST 是事实上的标准文档格式，
能够最大程度地与 Python 生态系统（PyPI、Sphinx）无缝集成。


.. _Python:     https://www.python.org/downloads/
.. _PyPI:       https://pypi.org/
.. _pip:        https://pip.pypa.io/en/stable/
.. _Requests:   https://requests.readthedocs.io/en/latest/
.. _FFmpeg:     https://www.ffmpeg.org/
.. _mkvmerge:   https://www.matroska.org/downloads/mkvtoolnix.html
.. _yt-dlp:     https://github.com/yt-dlp/yt-dlp
.. _youtube-dl: https://ytdl-org.github.io/youtube-dl/
.. _PySocks:    https://pypi.org/project/PySocks/
.. _brotli:     https://github.com/google/brotli
.. _brotlicffi: https://github.com/python-hyper/brotlicffi
.. _zstandard:  https://github.com/indygreg/python-zstandard
.. _PyYAML:     https://pyyaml.org/
.. _toml:       https://pypi.org/project/toml/
.. _SecretStorage: https://pypi.org/project/SecretStorage/
.. _Psycopg:    https://www.psycopg.org/
.. _truststore: https://truststore.readthedocs.io/en/latest/
.. _Jinja:      https://jinja.palletsprojects.com/
.. _Snapd:      https://docs.snapcraft.io/installing-snapd
.. _OAuth:      https://en.wikipedia.org/wiki/OAuth
.. _Chocolatey: https://chocolatey.org/install
.. _Scoop:      https://scoop.sh/
.. _Sphinx:     https://www.sphinx-doc.org/

.. |pypi| image:: https://img.shields.io/pypi/v/gallery-dl?logo=pypi&label=PyPI
    :target: https://pypi.org/project/gallery-dl/

.. |build| image:: https://github.com/mikf/gallery-dl/actions/workflows/tests.yml/badge.svg
    :target: https://github.com/mikf/gallery-dl/actions

.. |gitter| image:: https://badges.gitter.im/gallery-dl/main.svg
    :target: https://gitter.im/gallery-dl/main

.. |discord| image:: https://img.shields.io/discord/1067148002722062416?logo=discord&label=Discord&color=blue
    :target: https://discord.gg/rSzQwRvGnE
