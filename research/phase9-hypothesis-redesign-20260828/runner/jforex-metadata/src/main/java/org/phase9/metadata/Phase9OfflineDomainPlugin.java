package org.phase9.metadata;

import com.dukascopy.api.IDataService;
import com.dukascopy.api.IContext;
import com.dukascopy.api.ITimeDomain;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.plugins.IPluginContext;
import com.dukascopy.api.plugins.Plugin;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.channels.Channels;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Instant;
import java.util.Arrays;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

/** Evidence-only offline-domain probe.  It never creates canonical schedules. */
public final class Phase9OfflineDomainPlugin extends Plugin {
    private static final long START = Instant.parse("2013-01-01T00:00:00Z").toEpochMilli();
    private static final long M15_END_EXCLUSIVE =
            Instant.parse("2019-08-28T00:00:00Z").toEpochMilli();
    private static final long H1_END_EXCLUSIVE =
            Instant.parse("2019-08-01T00:00:00Z").toEpochMilli();
    private static final List<String> SYMBOLS = Arrays.asList(
            "AUD/JPY", "AUD/USD", "EUR/GBP", "EUR/JPY", "EUR/USD", "GBP/JPY",
            "GBP/USD", "USD/JPY", "XAU/USD", "XAG/USD", "BRENT.CMD/USD", "LIGHT.CMD/USD");
    private final Path evidenceDirectory;

    public Phase9OfflineDomainPlugin(Path evidenceDirectory) throws IOException {
        this.evidenceDirectory = Phase9MetadataClient.requirePrivateDirectory(evidenceDirectory);
    }

    @Override
    public void onStart(IPluginContext context) throws JFException {
        Path target = evidenceDirectory.resolve("OFFLINE_DOMAINS_RAW.tsv");
        FileAttribute<Set<PosixFilePermission>> mode0600 =
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"));
        try (SeekableByteChannel channel = Files.newByteChannel(
                    target,
                    EnumSet.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                    mode0600);
             BufferedWriter writer = new BufferedWriter(
                    Channels.newWriter(channel, StandardCharsets.US_ASCII.newEncoder(), -1))) {
            writer.write("provider_symbol\twindow\tquery_from_ms\tquery_to_ms\tdomain_start_ms\tdomain_end_ms\n");
            IContext dataContext = context;
            IDataService service = dataContext.getDataService();
            for (String symbol : SYMBOLS) {
                Instrument instrument = Instrument.fromString(symbol);
                if (instrument == null) {
                    throw new IllegalStateException("Frozen provider symbol did not resolve: " + symbol);
                }
                writeDomains(writer, service, symbol, "M15", instrument, M15_END_EXCLUSIVE);
                writeDomains(writer, service, symbol, "H1", instrument, H1_END_EXCLUSIVE);
            }
        } catch (IOException failure) {
            throw new JFException("Cannot seal private offline-domain evidence.", failure);
        } finally {
            context.stop();
        }
    }

    private static void writeDomains(
            BufferedWriter writer,
            IDataService service,
            String symbol,
            String window,
            Instrument instrument,
            long endExclusive) throws IOException, JFException {
        long queryTo = endExclusive - 1L;
        Set<ITimeDomain> domains = service.getOfflineTimeDomains(START, queryTo, instrument);
        for (ITimeDomain domain : domains) {
            writer.write(symbol);
            writer.write('\t');
            writer.write(window);
            writer.write('\t');
            writer.write(Long.toString(START));
            writer.write('\t');
            writer.write(Long.toString(queryTo));
            writer.write('\t');
            writer.write(Long.toString(domain.getStart()));
            writer.write('\t');
            writer.write(Long.toString(domain.getEnd()));
            writer.newLine();
        }
    }

    @Override
    public void onStop() throws JFException {
        // No strategy callbacks, subscriptions, orders, account values, bars, or ticks exist.
    }
}
