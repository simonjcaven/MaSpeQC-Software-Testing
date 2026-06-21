package utils;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class StringUtils {
    private static Pattern RE_WHITESPACE = Pattern.compile("^\\s*$");

    private StringUtils() {
        throw new AssertionError("This class can not be instantiated");
    }

    public static String stripLeading(String text, String prefix) {
        if (text.startsWith(prefix)) {
            return text.substring(prefix.length());
        }
        return text;
    }

    public static String sortedChars(String s) {
        char[] chars = s.toCharArray();
        Arrays.sort(chars);
        return new String(chars);
    }

    public static boolean isPureAscii(String text) {
        return StandardCharsets.US_ASCII.newEncoder().canEncode(text);
    }

    public static List<String> splitCommandLine(String line) {
        String pattern = "([\"'][^\"']+[\"']|[^\\s\"']+)";
        Pattern regex = Pattern.compile(pattern);
        Matcher matcher = regex.matcher(line);
        LinkedList<String> list = new LinkedList();
        while (matcher.find()) {
            list.add(matcher.group(1));
        }
        return list;
    }

    public static boolean isNullOrWhitespace(String s) {
        return s == null || s.length() == 0 || RE_WHITESPACE.matcher(s).matches();
    }

    public static String prependOnce(String base, String prefix) {
        if (base == null) {
            return prefix;
        }
        if (prefix == null) {
            return base;
        }
        return base.startsWith(prefix) ? base : prefix + base;
    }

    public static String appendOnce(String base, String suffix) {
        if (base == null) {
            return suffix;
        }
        if (suffix == null) {
            return base;
        }
        return base.endsWith(suffix) ? base : base + suffix;
    }

    public static String appendPrependOnce(String base, String quotes) {
        return StringUtils.prependOnce(StringUtils.appendOnce(base, quotes), quotes);
    }

    public static boolean isBlank(String s) {
        return StringUtils.isNullOrWhitespace(s);
    }

    public static boolean isNotBlank(String s) {
        return !StringUtils.isNullOrWhitespace(s);
    }

    public static String upToLastDot(String s) {
        int last = s.lastIndexOf(46);
        return last < 0 ? s : s.substring(0, last);
    }

    public static String afterLastDot(String s) {
        int last = s.lastIndexOf(46);
        return last < 0 ? "" : s.substring(last + 1);
    }

    public static String upToLastChar(String s, char ch, boolean emptyIfNoChar) {
        int last = s.lastIndexOf(ch);
        if (!(last >= 0)) {
            return emptyIfNoChar ? "" : s;
        }
        return s.substring(0, last);
    }

    public static String upToLastSubstr(String s, String substr, boolean emptyIfNoSubstr) {
        int last = s.lastIndexOf(substr);
        if (!(last >= 0)) {
            return emptyIfNoSubstr ? "" : s;
        }
        return s.substring(0, last);
    }

    public static String afterLastChar(String s, char ch, boolean emptyIfNoChar) {
        int last = s.lastIndexOf(ch);
        if (!(last >= 0)) {
            return emptyIfNoChar ? "" : s;
        }
        return s.substring(last + 1);
    }

    public static String join(Iterable<?> iterable, String separator) {
        if (iterable == null) {
            return null;
        }
        return StringUtils.join(iterable.iterator(), separator);
    }

    public static String join(Iterator<?> iterator, String separator) {
        if (iterator == null) {
            return null;
        }
        if (!iterator.hasNext()) {
            return "";
        }
        Object first = iterator.next();
        if (!iterator.hasNext()) {
            String result = Objects.toString(first);
            return result;
        }
        StringBuilder buf = new StringBuilder(256);
        if (first != null) {
            buf.append(first);
        }
        while (iterator.hasNext()) {
            if (separator == null) continue;
            buf.append(separator);
            Object obj = iterator.next();
            if (obj == null) continue;
            buf.append(obj);
        }
        return buf.toString();
    }

    public static <T extends Enum<T>> T getEnumFromString(Class<T> c, String string) {
        if (c != null && string != null) {
            return Enum.valueOf(c, string.trim().toUpperCase());
        }
        return null;
    }

    public static void wrap(String text, int indent, int colSize, StringBuilder out) {
        String[] words = text.split("[ \\t]");
        int i = 0;
        int caretPos = 0;
        while (i < words.length) {
            String word = words[i];
            caretPos = caretPos + word.length();
            if (caretPos <= colSize) {
                out.append(word);
                if (caretPos != colSize) {
                    if (word.endsWith("\n")) continue;
                    out.append(" ");
                }
                i++;
            } else {
                caretPos = 0;
                out.append("\n").append(StringUtils.repeat(" ", indent));
                caretPos = caretPos + indent;
            }
        }
    }

    public static String repeat(String str, int i) {
        return i > 0 ? new String(new char[i]).replace("\u0000", str) : "";
    }

    public static boolean isBlank(CharSequence cs) {
        int tmp0 = cs.length();
        int strLen = tmp0;
        if (cs == null || tmp0 == 0) {
            return true;
        }
        for (int i = 0; i < strLen; i++) {
            if (Character.isWhitespace(cs.charAt(i))) continue;
            return false;
        }
        return true;
    }
}
