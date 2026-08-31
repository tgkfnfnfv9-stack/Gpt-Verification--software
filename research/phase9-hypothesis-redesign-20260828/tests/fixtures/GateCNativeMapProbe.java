package org.phase9.gatec;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Inert C1 probe: explicit native loads and /proc maps only; no SDK or network calls. */
public final class GateCNativeMapProbe {
    private GateCNativeMapProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException("Expected one native path, a ready file, and a release file.");
        }
        Path first = Paths.get(args[0]).toRealPath();
        Path ready = Paths.get(args[1]).toAbsolutePath().normalize();
        Path release = Paths.get(args[2]).toAbsolutePath().normalize();
        System.load(first.toString());
        String pid = Paths.get("/proc/self").toRealPath().getFileName().toString();
        Files.write(ready, (pid + "\n").getBytes("UTF-8"));
        long deadline = System.currentTimeMillis() + 30000L;
        while (!Files.isRegularFile(release)) {
            if (System.currentTimeMillis() >= deadline) {
                throw new IllegalStateException("Supervisor did not release the native map probe.");
            }
            Thread.sleep(25L);
        }
        System.out.println("gate_c_native_map_probe=PASS");
    }
}
