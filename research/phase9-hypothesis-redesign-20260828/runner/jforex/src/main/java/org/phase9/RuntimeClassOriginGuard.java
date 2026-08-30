package org.phase9;

import java.io.IOException;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.FileVisitResult;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.CodeSource;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

/**
 * Fail-closed Java agent that prevents JForex from executing bytecode outside
 * the reproducibly built shaded runner JAR or the pinned Java runtime.
 */
public final class RuntimeClassOriginGuard {
    private static final String REQUIRED_INFLATION_THRESHOLD = "2147483647";
    private static final char[] HEX = "0123456789abcdef".toCharArray();
    private static final MessageDigest SHA_256 = newSha256();
    private static final AtomicLong CHECKED = new AtomicLong();
    private static volatile Path auditPath;
    private static volatile URI runnerOrigin;
    private static volatile Path javaHome;
    private static volatile Map<URI, Map<String, Set<String>>> approvedClassHashes;
    private static volatile boolean active;

    private RuntimeClassOriginGuard() {}

    public static void premain(String agentArguments, Instrumentation instrumentation) {
        try {
            if (agentArguments == null || agentArguments.trim().isEmpty()) {
                throw new IllegalArgumentException("Class-origin audit path is required.");
            }
            auditPath = Paths.get(agentArguments).toAbsolutePath().normalize();
            Path parent = auditPath.getParent();
            if (parent == null || !Files.isDirectory(parent) || Files.exists(auditPath)) {
                throw new IllegalArgumentException("Class-origin audit path must be new in an existing directory.");
            }
            if (!REQUIRED_INFLATION_THRESHOLD.equals(
                    System.getProperty("sun.reflect.inflationThreshold"))) {
                throw new IllegalStateException(
                        "Java 8 reflection inflation must be disabled by the pinned threshold.");
            }
            runnerOrigin = normalizedOrigin(RuntimeClassOriginGuard.class.getProtectionDomain());
            javaHome = Paths.get(System.getProperty("java.home")).toAbsolutePath().normalize();
            if (runnerOrigin == null || !"file".equalsIgnoreCase(runnerOrigin.getScheme())) {
                throw new IllegalStateException("Runner must have an exact local file origin.");
            }
            approvedClassHashes = loadApprovedClassHashes(Paths.get(runnerOrigin));
            if (!"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
                    .equals(sha256("abc".getBytes(StandardCharsets.US_ASCII)))) {
                throw new IllegalStateException("SHA-256 self-test failed.");
            }
            append(
                    "guard_status=ACTIVE\n"
                            + "runner_origin=" + runnerOrigin + "\n"
                            + "java_home=" + javaHome + "\n"
                            + "reflection_inflation_threshold=" + REQUIRED_INFLATION_THRESHOLD + "\n"
                            + "approved_class_names=" + approvedClassNameCount(approvedClassHashes) + "\n");

            verifyAlreadyLoaded(instrumentation);
            instrumentation.addTransformer(new Guard(), false);
            active = true;
            Runtime.getRuntime().addShutdownHook(new AuditShutdownHook());
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("Cannot initialize Phase 9 class-origin guard.", error);
        }
    }

    public static void assertActive() {
        if (!active) {
            throw new IllegalStateException("Phase 9 runtime class-origin guard is not active.");
        }
    }

    private static void verifyAlreadyLoaded(Instrumentation instrumentation) throws Exception {
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            String className = type.getName().replace('.', '/');
            if (!allowed(
                    type.getClassLoader(),
                    className,
                    type.getProtectionDomain(),
                    loadedClassBytes(type, className))) {
                rejectAndHalt(type.getName().replace('.', '/'), type.getProtectionDomain());
            }
        }
    }

    private static final class Guard implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {
            CHECKED.incrementAndGet();
            boolean permitted;
            try {
                permitted = allowed(loader, className, protectionDomain, classfileBuffer);
            } catch (Throwable error) {
                rejectAndHalt(
                        className,
                        protectionDomain,
                        "guard_exception:" + error.getClass().getName());
                return null;
            }
            if (!permitted) {
                rejectAndHalt(className, protectionDomain);
            }
            return null;
        }
    }

    private static final class AuditShutdownHook extends Thread {
        AuditShutdownHook() {
            super("phase9-class-origin-audit");
        }

        @Override
        public void run() {
            try {
                append("guard_status=PASSED\nchecked_classes=" + CHECKED.get() + "\n");
            } catch (RuntimeException ignored) {
                // The workflow also requires the PASSED marker, so a write failure remains fail-closed.
            }
        }
    }

    private static boolean allowed(
            ClassLoader loader, String className, ProtectionDomain domain, byte[] classBytes) {
        if (loader == null) {
            return true;
        }
        URI origin = normalizedOrigin(domain);
        Map<String, Set<String>> archiveHashes =
                origin == null ? null : approvedClassHashes.get(origin);
        Set<String> hashes = archiveHashes == null ? null : archiveHashes.get(className);
        return archiveHashes != null
                && classBytes != null
                && hashes != null
                && hashes.contains(sha256(classBytes));
    }

    private static URI normalizedOrigin(ProtectionDomain domain) {
        if (domain == null) {
            return null;
        }
        CodeSource source = domain.getCodeSource();
        if (source == null || source.getLocation() == null) {
            return null;
        }
        try {
            return source.getLocation().toURI().normalize();
        } catch (URISyntaxException error) {
            throw new IllegalStateException("Invalid class code-source URI.", error);
        }
    }

    private static void rejectAndHalt(String className, ProtectionDomain domain) {
        rejectAndHalt(className, domain, "policy_mismatch");
    }

    private static void rejectAndHalt(
            String className, ProtectionDomain domain, String reason) {
        String origin;
        try {
            origin = String.valueOf(normalizedOrigin(domain));
        } catch (Throwable error) {
            origin = "unavailable:" + error.getClass().getName();
        }
        try {
            append(
                    "guard_status=REJECTED\n"
                            + "rejection_reason=" + reason + "\n"
                            + "rejected_class=" + String.valueOf(className) + "\n"
                            + "rejected_origin=" + origin + "\n");
        } catch (Throwable ignored) {
            // Runtime halt is mandatory even when audit evidence cannot be written.
        }
        Runtime.getRuntime().halt(86);
        throw new AssertionError("Runtime.halt unexpectedly returned.");
    }

    private static Map<URI, Map<String, Set<String>>> loadApprovedClassHashes(Path runner)
            throws IOException {
        Map<URI, Map<String, Set<String>>> archives = new HashMap<>();
        Path exactRunner = runner.toRealPath();
        addApprovedArchive(exactRunner, archives);
        final List<Path> runtimeArchives = new ArrayList<>();
        Files.walkFileTree(javaHome, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) {
                if (attributes.isRegularFile() && file.getFileName().toString().endsWith(".jar")) {
                    runtimeArchives.add(file);
                }
                return FileVisitResult.CONTINUE;
            }
        });
        Collections.sort(runtimeArchives);
        for (Path archive : runtimeArchives) {
            Path exactArchive = archive.toRealPath();
            addApprovedArchive(exactArchive, archives);
        }
        return Collections.unmodifiableMap(
                new HashMap<URI, Map<String, Set<String>>>(archives));
    }

    private static void addApprovedArchive(
            Path archive, Map<URI, Map<String, Set<String>>> archives) throws IOException {
        URI origin = archive.toUri().normalize();
        if (archives.containsKey(origin)) {
            throw new IllegalStateException("Duplicate approved archive origin: " + origin);
        }
        Map<String, Set<String>> hashes = new HashMap<>();
        addJarClassHashes(archive, hashes);
        Map<String, Set<String>> frozen = new HashMap<>();
        for (Map.Entry<String, Set<String>> entry : hashes.entrySet()) {
            frozen.put(
                    entry.getKey(),
                    Collections.unmodifiableSet(new HashSet<String>(entry.getValue())));
        }
        archives.put(origin, Collections.unmodifiableMap(frozen));
    }

    private static int approvedClassNameCount(
            Map<URI, Map<String, Set<String>>> archives) {
        Set<String> names = new HashSet<>();
        for (Map<String, Set<String>> archive : archives.values()) {
            names.addAll(archive.keySet());
        }
        return names.size();
    }

    private static void addJarClassHashes(Path archive, Map<String, Set<String>> hashes) throws IOException {
        try (JarFile jar = new JarFile(archive.toFile())) {
            java.util.Enumeration<JarEntry> entries = jar.entries();
            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                String name = entry.getName();
                if (entry.isDirectory() || !name.endsWith(".class") || name.startsWith("META-INF/versions/")) {
                    continue;
                }
                try (InputStream input = jar.getInputStream(entry)) {
                    byte[] bytes = readAll(input);
                    String className = name.substring(0, name.length() - 6);
                    Set<String> classHashes = hashes.get(className);
                    if (classHashes == null) {
                        classHashes = new HashSet<>();
                        hashes.put(className, classHashes);
                    }
                    classHashes.add(sha256(bytes));
                }
            }
        }
    }

    private static byte[] loadedClassBytes(Class<?> type, String className) throws IOException {
        ClassLoader loader = type.getClassLoader();
        if (loader == null) {
            return null;
        }
        try (InputStream input = loader.getResourceAsStream(className + ".class")) {
            return input == null ? null : readAll(input);
        }
    }

    private static byte[] readAll(InputStream input) throws IOException {
        java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        for (int read = input.read(buffer); read >= 0; read = input.read(buffer)) {
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable.", error);
        }
    }

    private static synchronized String sha256(byte[] bytes) {
        byte[] digest = SHA_256.digest(bytes);
        char[] value = new char[digest.length * 2];
        for (int index = 0; index < digest.length; index++) {
            int item = digest[index] & 0xff;
            value[index * 2] = HEX[item >>> 4];
            value[index * 2 + 1] = HEX[item & 0x0f];
        }
        return new String(value);
    }

    private static synchronized void append(String value) {
        try {
            Files.write(
                    auditPath,
                    value.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND,
                    StandardOpenOption.WRITE);
        } catch (IOException error) {
            throw new IllegalStateException("Cannot write class-origin audit evidence.", error);
        }
    }
}
