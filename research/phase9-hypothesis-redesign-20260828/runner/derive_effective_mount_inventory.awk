{
  count++
  ids[count] = $1
  parents[count] = $2
  targets[count] = $5
  options[count] = $6
  separator = 0
  for (field = 7; field <= NF; field++) {
    if ($field == "-") {
      separator = field
      break
    }
  }
  if (separator == 0) {
    malformed = 1
  }
}

END {
  if (malformed || count == 0) {
    exit 2
  }
  for (record = 1; record <= count; record++) {
    shadowed = 0
    for (candidate = 1; candidate <= count; candidate++) {
      if (parents[candidate] == ids[record] && targets[candidate] == targets[record]) {
        shadowed = 1
        break
      }
    }
    if (!shadowed) {
      print targets[record], options[record]
    }
  }
}
