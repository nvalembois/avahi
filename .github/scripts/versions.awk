$1 == "ARG" && $2 ~ /^[A-Z_]+_VERSION=/ { 
  print $2
}
$1 == "FROM" {
  i = split($2, from, ":")
  j = split(from[1], img, "/")
  gsub("(-.*)?@.*", "", from[2])
  print toupper(img[j]) "_VERSION=" from[2]
}
