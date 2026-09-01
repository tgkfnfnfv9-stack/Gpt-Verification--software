package org.phase9.metadata;

import com.dukascopy.api.plugins.Plugin;
import com.dukascopy.api.system.IClient;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * Dedicated metadata client facade.  It is deliberately not executable and is
 * physically separate from the Phase 9 price acquirer.
 */
public final class Phase9MetadataClient {
    public static final String DEMO_JNLP =
            "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp";

    private Phase9MetadataClient() {}

    public static UUID connectAndRun(
            IClient client,
            String exactJnlp,
            String username,
            String password,
            File privateCacheDirectory,
            Path privateEvidenceDirectory) throws Exception {
        Objects.requireNonNull(client, "client");
        Objects.requireNonNull(username, "username");
        Objects.requireNonNull(password, "password");
        Objects.requireNonNull(privateCacheDirectory, "privateCacheDirectory");
        Objects.requireNonNull(privateEvidenceDirectory, "privateEvidenceDirectory");
        if (!DEMO_JNLP.equals(exactJnlp)) {
            throw new SecurityException("Unexpected JNLP identity.");
        }
        Path validatedCache = requirePrivateDirectory(privateCacheDirectory.toPath());
        Path validatedEvidence = requirePrivateDirectory(privateEvidenceDirectory);
        client.setCacheDirectory(validatedCache.toFile());
        requirePrivateDirectory(validatedCache);
        requirePrivateDirectory(validatedEvidence);
        client.connect(exactJnlp, username, password);
        if (!client.isConnected()) {
            throw new IllegalStateException("Metadata client did not connect.");
        }
        Plugin plugin = new Phase9OfflineDomainPlugin(validatedEvidence);
        return client.runPlugin(plugin, null);
    }

    static Path requirePrivateDirectory(Path candidate) throws IOException {
        Path absolute = candidate.toAbsolutePath().normalize();
        if (!Files.isDirectory(absolute, LinkOption.NOFOLLOW_LINKS)
                || !absolute.toRealPath().equals(absolute)) {
            throw new SecurityException("Metadata custody path contains a symlink or is not a directory.");
        }
        Set<PosixFilePermission> expected = EnumSet.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE);
        if (!Files.getPosixFilePermissions(absolute, LinkOption.NOFOLLOW_LINKS).equals(expected)) {
            throw new SecurityException("Metadata custody directory must be mode 0700.");
        }
        return absolute;
    }

    public static void main(String[] ignored) {
        throw new SecurityException(
                "No executable dispatch is authorized; use a later frozen manual workflow.");
    }
}
