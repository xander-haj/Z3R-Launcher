#!/usr/bin/env bash
set -euo pipefail

appdir="${1:?Usage: prepare-gtk-runtime.sh APPDIR}"
multiarch="$(gcc -print-multiarch 2>/dev/null || dpkg-architecture -qDEB_HOST_MULTIARCH)"
lib_root="${appdir}/usr/lib/${multiarch}"

mkdir -p "${lib_root}" "${appdir}/usr/etc" "${appdir}/usr/share" "${appdir}/lib"

if [ ! -e "${appdir}/lib/${multiarch}" ]; then
  ln -s "../usr/lib/${multiarch}" "${appdir}/lib/${multiarch}"
fi

copy_file() {
  local source="$1"
  local destination="$2"

  if [ -e "${source}" ]; then
    install -Dm755 "${source}" "${destination}"
  fi
}

copy_tree() {
  local source="$1"
  local destination="$2"

  if [ -d "${source}" ]; then
    mkdir -p "$(dirname "${destination}")"
    cp -a "${source}" "${destination}"
  fi
}

copy_tree_contents() {
  local source="$1"
  local destination="$2"

  if [ -d "${source}" ]; then
    mkdir -p "${destination}"
    cp -a "${source}/." "${destination}/"
  fi
}

relocate_usr_paths() {
  local target="$1"

  if [ -f "${target}" ]; then
    perl -0pi -e 's#/usr#././#g' "${target}"
  fi
}

should_copy_shared_object() {
  local source="$1"
  local filename

  filename="$(basename "${source}")"

  case "${source}" in
    */dri/*|*/vulkan/*)
      return 1
      ;;
  esac

  case "${filename}" in
    ld-linux-*|libBrokenLocale.so.*|libanl.so.*|libc.so.*|libdl.so.*|libm.so.*)
      return 1
      ;;
    libmvec.so.*|libnsl.so.*|libpthread.so.*|libresolv.so.*|librt.so.*|libthread_db.so.*|libutil.so.*)
      return 1
      ;;
    libgcc_s.so.*|libstdc++.so.*)
      return 1
      ;;
    libEGL.so.*|libEGL_mesa.so.*|libGL.so.*|libGLESv1_CM.so.*|libGLESv2.so.*|libGLX.so.*)
      return 1
      ;;
    libGLX_mesa.so.*|libGLdispatch.so.*|libOpenGL.so.*|libdrm.so.*|libgbm.so.*)
      return 1
      ;;
    libglapi.so.*|libvulkan.so.*|libvulkan_*.so*|libVkLayer_*.so*)
      return 1
      ;;
  esac

  return 0
}

copy_shared_object() {
  local source="$1"

  if ! should_copy_shared_object "${source}"; then
    return
  fi

  if [ -e "${source}" ]; then
    cp -L "${source}" "${lib_root}/$(basename "${source}")"
  fi
}

copy_dependencies() {
  local target="$1"

  if [ ! -e "${target}" ]; then
    return
  fi

  ldd "${target}" |
    awk '/=> \// { print $3 } /^\// { print $1 }' |
    sort -u |
    while read -r dependency; do
      copy_shared_object "${dependency}"
    done
}

copy_matching_shared_objects() {
  local pattern="$1"
  local found=0

  for source in ${pattern}; do
    if [ -e "${source}" ]; then
      found=1
      copy_shared_object "${source}"
      copy_dependencies "${source}"
    fi
  done

  return 0
}

copy_webkit_runtime() {
  local api="$1"
  local helper_dir="/usr/lib/${multiarch}/webkit2gtk-${api}"

  copy_tree "${helper_dir}" "${lib_root}/webkit2gtk-${api}"
  copy_tree "/usr/libexec/webkit2gtk-${api}" "${appdir}/usr/libexec/webkit2gtk-${api}"
  copy_tree "/usr/share/webkitgtk-${api}" "${appdir}/usr/share/webkitgtk-${api}"

  if [ -d "${lib_root}/webkit2gtk-${api}" ]; then
    find "${lib_root}/webkit2gtk-${api}" -type f -perm -111 -print |
      while read -r helper; do
        copy_dependencies "${helper}"
      done
  fi
}

relocate_webkit_runtime() {
  local api="$1"
  local target

  for target in "${lib_root}/libwebkit2gtk-${api}.so"* "${lib_root}/libjavascriptcoregtk-${api}.so"*; do
    if [ -e "${target}" ]; then
      relocate_usr_paths "${target}"
    fi
  done

  if [ -d "${lib_root}/webkit2gtk-${api}" ]; then
    find "${lib_root}/webkit2gtk-${api}" -type f -print |
      while read -r target; do
        relocate_usr_paths "${target}"
      done
  fi
}

require_relocated_webkit_runtime() {
  local api="$1"
  local target
  local absolute_path="/usr/lib/${multiarch}/webkit2gtk-${api}"

  for target in "${lib_root}/libwebkit2gtk-${api}.so"*; do
    if [ -e "${target}" ] && grep -a -q "${absolute_path}" "${target}"; then
      echo "WebKitGTK still contains non-relocatable helper path: ${absolute_path}" >&2
      exit 1
    fi
  done
}

require_typelib() {
  local namespace="$1"
  local search_root="$2"

  if [ ! -f "${search_root}/${namespace}.typelib" ]; then
    echo "Missing required GObject typelib: ${namespace}.typelib" >&2
    echo "Searched: ${search_root}" >&2
    find "${appdir}/usr/lib" -path "*/girepository-1.0/*.typelib" -print | sort >&2 || true
    exit 1
  fi
}

detect_webkit_api() {
  local search_root="$1"

  if [ -f "${search_root}/WebKit2-4.1.typelib" ]; then
    echo "4.1"
    return
  fi
  if [ -f "${search_root}/WebKit2-4.0.typelib" ]; then
    echo "4.0"
    return
  fi

  echo "Missing required GObject typelib: WebKit2-4.1.typelib or WebKit2-4.0.typelib" >&2
  echo "Searched: ${search_root}" >&2
  find "${appdir}/usr/lib" -path "*/girepository-1.0/*.typelib" -print | sort >&2 || true
  exit 1
}

copy_matching_shared_objects "/usr/lib/${multiarch}/libwebkit2gtk-4.1.so"* || true
copy_matching_shared_objects "/usr/lib/${multiarch}/libjavascriptcoregtk-4.1.so"* || true
copy_matching_shared_objects "/usr/lib/${multiarch}/libwebkit2gtk-4.0.so"* || true
copy_matching_shared_objects "/usr/lib/${multiarch}/libjavascriptcoregtk-4.0.so"* || true
copy_matching_shared_objects "/usr/lib/${multiarch}/libgtk-3.so"* || true

copy_webkit_runtime "4.1"
copy_webkit_runtime "4.0"
relocate_webkit_runtime "4.1"
relocate_webkit_runtime "4.0"
require_relocated_webkit_runtime "4.1"
require_relocated_webkit_runtime "4.0"
copy_tree_contents "/usr/lib/${multiarch}/girepository-1.0" "${lib_root}/girepository-1.0"
copy_tree_contents "/usr/lib/girepository-1.0" "${lib_root}/girepository-1.0"
copy_tree_contents "${lib_root}/girepository-1.0" "${appdir}/usr/lib/girepository-1.0"
copy_tree "/usr/lib/${multiarch}/gtk-3.0" "${lib_root}/gtk-3.0"
copy_tree "/usr/lib/${multiarch}/gdk-pixbuf-2.0" "${lib_root}/gdk-pixbuf-2.0"
copy_tree "/usr/lib/${multiarch}/gio/modules" "${lib_root}/gio/modules"
copy_tree "/etc/fonts" "${appdir}/usr/etc/fonts"
copy_tree "/usr/share/glib-2.0" "${appdir}/usr/share/glib-2.0"
copy_tree "/usr/share/fontconfig" "${appdir}/usr/share/fontconfig"

webkit_api="$(detect_webkit_api "${lib_root}/girepository-1.0")"
if [ "${webkit_api}" = "4.1" ]; then
  soup_api="3.0"
else
  soup_api="2.4"
fi

require_typelib "Gtk-3.0" "${lib_root}/girepository-1.0"
require_typelib "Gdk-3.0" "${lib_root}/girepository-1.0"
require_typelib "WebKit2-${webkit_api}" "${lib_root}/girepository-1.0"
require_typelib "JavaScriptCore-${webkit_api}" "${lib_root}/girepository-1.0"
require_typelib "Soup-${soup_api}" "${lib_root}/girepository-1.0"

if command -v glib-compile-schemas >/dev/null 2>&1 && [ -d "${appdir}/usr/share/glib-2.0/schemas" ]; then
  glib-compile-schemas "${appdir}/usr/share/glib-2.0/schemas"
fi

for loader in "${lib_root}/gdk-pixbuf-2.0"/*/loaders/*.so; do
  if [ -e "${loader}" ]; then
    copy_dependencies "${loader}"
  fi
done

for module in "${lib_root}/gio/modules"/*.so; do
  if [ -e "${module}" ]; then
    copy_dependencies "${module}"
  fi
done

copy_file "/usr/bin/gdk-pixbuf-query-loaders" "${appdir}/usr/bin/gdk-pixbuf-query-loaders"
copy_dependencies "/usr/bin/gdk-pixbuf-query-loaders"
