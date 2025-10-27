# Maintainer: Bill Sideris <bill88t@bredos.org>

pkgname=bredos-govctl
pkgver=1.2.2
pkgrel=1
pkgdesc="BredOS CPU/devfreq governor manager"

arch=('any')
url="https://BredOS.org/"
license=('GPL3')

groups=(bredos)
depends=('python' 'systemd')

backup=('etc/govctl/config.json')
source=('govctl_service.py'
        'govctl_cli.py'
        'govctl.service'
        'default_config.json'
        'govctl.8')

sha256sums=('e6ea5d2e4d680357df4518c398b360d1e303f08332418a736052d1a83daaaf13'
            'd20f437916f6dbe853ae7ffd0995a950e7c8eed57691b8b829f0a352fdbc881c'
            '8a098c350416e3fe789cceb4d0fb5902fb9fed4e56abdf28cb989b4bd8c4923b'
            '9d10c81fff99c57d2eabad9adc3298b84d24dad390dd784ab7ac08d6650a2afb'
            'e8ea1f038dfeaf86e8008a61d05cd4ba0a7ca33c3a7c71894749b0330b4c2364')

install=govctl.install

package() {
    install -Dm755 govctl_service.py "${pkgdir}/usr/bin/govctl_service.py"
    install -Dm755 govctl_cli.py "${pkgdir}/usr/bin/govctl"

    install -Dm644 govctl.service "${pkgdir}/usr/lib/systemd/system/govctl.service"

    install -d "${pkgdir}/etc/govctl/"
    install -Dm644 default_config.json "${pkgdir}/etc/govctl/config.json"

    # Install man page
    install -Dm644 govctl.8 "${pkgdir}/usr/share/man/man8/govctl.8"
}
