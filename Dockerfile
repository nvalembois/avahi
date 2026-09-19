# renovate: datasource=github-releases depName=avahi/avahi
ARG AVAHI_VERSION=0.8

FROM docker.io/library/alpine:3.24.2 AS base

FROM base AS builder

ARG AVAHI_VERSION

RUN apk add --no-cache build-base automake autoconf libtool pkgconfig \
                     expat-dev libdaemon-dev gettext-dev intltool libevent-dev \
                     libcap

RUN wget https://github.com/avahi/avahi/releases/download/v${AVAHI_VERSION}/avahi-${AVAHI_VERSION}.tar.gz \
    && tar xzf avahi-${AVAHI_VERSION}.tar.gz \
    && rm avahi-${AVAHI_VERSION}.tar.gz

WORKDIR /avahi-${AVAHI_VERSION}
RUN ./configure \
      --prefix='' \
      --disable-shared \
      --disable-static \
      --disable-libevent \
      --disable-dbus \
      --disable-dbm \
      --disable-gdbm \
      --disable-gtk \
      --disable-gtk3 \
      --disable-qt3 --disable-qt4 --disable-qt5 \
      --disable-python \
      --disable-mono \
      --disable-monodoc \
      --disable-doxygen-doc \
      --disable-manpages \
      --disable-xmltoman \
      --disable-glib \
      --disable-gobject \
      --disable-dbus \
      --disable-autoipd \
      --with-distro=none \
    && make -j$(nproc) \
    && make install DESTDIR=/out \
    && setcap 'cap_net_bind_service=+ep,cap_net_raw=+ep' /out/sbin/avahi-daemon \
    && rm -r /out/lib /out/include /out/sbin/avahi-dnsconfd /out/share/avahi \
             /out/etc/avahi/services/* /out/etc/avahi/avahi-dnsconfd.action

FROM base

COPY --from=builder /out/ /

RUN apk add --no-cache libdaemon libexpat libintl \
 && addgroup -S avahi \
 && adduser -S -D -H -h /var/run/avahi-daemon -s /sbin/nologin -G avahi -g "Avahi mDNS daemon" avahi \
 && addgroup avahi netdev \
 && mkdir -p /var/run/avahi-daemon \
 && chown avahi:avahi /var/run/avahi-daemon \
 && chmod 755 /var/run/avahi-daemon

USER avahi

EXPOSE 5353/udp
ENTRYPOINT ["/sbin/avahi-daemon", "--no-drop-root", "--no-rlimits", "--no-proc-title", "-f", "/etc/avahi/avahi-daemon.conf"]