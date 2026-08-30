package org.phase9;

import com.dukascopy.api.IAccount;
import com.dukascopy.api.IBar;
import com.dukascopy.api.IContext;
import com.dukascopy.api.IMessage;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.LoadingProgressListener;
import com.dukascopy.api.OfferSide;
import com.dukascopy.api.Period;
import com.dukascopy.api.system.ISystemListener;
import com.dukascopy.api.system.ITesterClient;
import com.dukascopy.api.system.TesterFactory;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Acquisition-only JForex Tester client. It cannot accept date arguments or trade. */
public final class Phase9JForexAcquirer {
    private static final String JNLP_URL = "https://platform.dukascopy.com/demo_3/jforex_3.jnlp";
    private static final String CONFIRMATION = "ACQUIRE_PHASE9_JFOREX_FROZEN_INTERVALS_ONLY";
    private static final long START = Instant.parse("2013-01-01T00:00:00Z").toEpochMilli();
    private static final long M15_END_EXCLUSIVE = Instant.parse("2019-08-28T00:00:00Z").toEpochMilli();
    private static final long H1_END_EXCLUSIVE = Instant.parse("2019-08-01T00:00:00Z").toEpochMilli();
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT.withZone(ZoneOffset.UTC);

    private static final Map<String, String> SYMBOLS;
    static {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("AUDJPY", "AUD/JPY");
        values.put("AUDUSD", "AUD/USD");
        values.put("EURGBP", "EUR/GBP");
        values.put("EURJPY", "EUR/JPY");
        values.put("EURUSD", "EUR/USD");
        values.put("GBPJPY", "GBP/JPY");
        values.put("GBPUSD", "GBP/USD");
        values.put("USDJPY", "USD/JPY");
        values.put("XAUUSD", "XAU/USD");
        values.put("XAGUSD", "XAG/USD");
        values.put("BRENTCMDUSD", "BRENT.CMD/USD");
        values.put("LIGHTCMDUSD", "LIGHT.CMD/USD");
        SYMBOLS = Collections.unmodifiableMap(values);
    }

    private Phase9JForexAcquirer() {}

    public static void main(String[] args) throws Exception {
        Arguments parsed = Arguments.parse(args);
        if (!CONFIRMATION.equals(System.getenv("PHASE9_JFOREX_CONFIRM"))) {
            throw new IllegalStateException("Exact Phase 9 JForex acquisition confirmation is required.");
        }
        String username = requiredSecret("DUKASCOPY_USERNAME");
        String password = requiredSecret("DUKASCOPY_PASSWORD");
        assertOutsideCheckout(parsed.outputDirectory);
        if (!Files.isDirectory(parsed.outputDirectory)) {
            throw new IllegalArgumentException("Output directory must already exist.");
        }

        Period period = parsed.timeframe.equals("M15") ? Period.FIFTEEN_MINS : Period.ONE_HOUR;
        OfferSide side = parsed.side.equals("bid") ? OfferSide.BID : OfferSide.ASK;
        long endExclusive = parsed.timeframe.equals("M15") ? M15_END_EXCLUSIVE : H1_END_EXCLUSIVE;
        Set<Instrument> instruments = resolveInstruments();
        CountDownLatch finished = new CountDownLatch(1);
        ITesterClient client = TesterFactory.getDefaultInstance();
        client.setCacheDirectory(parsed.cacheDirectory.toFile());
        client.setSystemListener(new ISystemListener() {
            @Override public void onStart(long processId) { System.out.println("tester_started=" + processId); }
            @Override public void onStop(long processId) { finished.countDown(); }
            @Override public void onConnect() { System.out.println("tester_connected=true"); }
            @Override public void onDisconnect() { System.err.println("Tester disconnected."); }
        });

        try {
            client.connect(JNLP_URL, username, password);
            for (int remaining = 60; remaining > 0 && !client.isConnected(); remaining--) {
                Thread.sleep(1000L);
            }
            if (!client.isConnected()) {
                throw new IllegalStateException("Failed to connect to the authenticated JForex Tester service.");
            }
            if (!client.getAvailableInstruments().containsAll(instruments)) {
                Set<Instrument> missing = new LinkedHashSet<>(instruments);
                missing.removeAll(client.getAvailableInstruments());
                throw new IllegalStateException("Registered instruments unavailable for this account: " + missing);
            }
            client.setSubscribedInstruments(instruments);
            client.setDataInterval(
                    period,
                    side,
                    ITesterClient.InterpolationMethod.FOUR_TICKS,
                    START,
                    endExclusive - 1L);
            ProgressStatus downloadStatus = new ProgressStatus("preload");
            Future<?> download = client.downloadData(downloadStatus);
            download.get();
            downloadStatus.assertComplete();

            BarWriterStrategy strategy = new BarWriterStrategy(
                    parsed.outputDirectory, parsed.timeframe, period, side, START, endExclusive);
            ProgressStatus strategyStatus = new ProgressStatus("strategy");
            client.startStrategy(strategy, strategyStatus);
            if (!finished.await(90, TimeUnit.MINUTES)) {
                throw new IllegalStateException("Tester strategy did not finish within 90 minutes.");
            }
            strategyStatus.assertComplete();
            strategy.assertSuccessful();
        } finally {
            if (client.isConnected()) {
                client.disconnect();
            }
        }
    }

    private static final class ProgressStatus implements LoadingProgressListener {
        private final String stage;
        private final AtomicBoolean finished = new AtomicBoolean(false);
        private final AtomicBoolean allLoaded = new AtomicBoolean(false);

        ProgressStatus(String stage) {
            this.stage = stage;
        }

        @Override public void dataLoaded(long start, long end, long current, String information) {}

        @Override public void loadingFinished(boolean complete, long start, long end, long current) {
            allLoaded.set(complete);
            finished.set(true);
            if (!complete) {
                System.err.println("JForex reported incomplete data loading for " + stage + ".");
            }
        }

        @Override public boolean stopJob() { return false; }

        void assertComplete() {
            if (!finished.get() || !allLoaded.get()) {
                throw new IllegalStateException("JForex data loading did not complete for " + stage + ".");
            }
        }
    }

    private static Set<Instrument> resolveInstruments() {
        Set<Instrument> instruments = new LinkedHashSet<>();
        for (String providerSymbol : SYMBOLS.values()) {
            Instrument instrument = Instrument.fromString(providerSymbol);
            if (instrument == null) {
                throw new IllegalStateException("JForex SDK cannot resolve registered symbol " + providerSymbol);
            }
            instruments.add(instrument);
        }
        if (instruments.size() != 12) {
            throw new IllegalStateException("JForex mapping must resolve to exactly 12 unique instruments.");
        }
        return instruments;
    }

    private static String requiredSecret(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalStateException("Required GitHub secret is not configured: " + name);
        }
        return value;
    }

    private static void assertOutsideCheckout(Path output) throws IOException {
        String workspace = System.getenv("GITHUB_WORKSPACE");
        if (workspace == null || workspace.trim().isEmpty()) {
            return;
        }
        Path checkout = Paths.get(workspace).toRealPath();
        Path resolved = output.toAbsolutePath().normalize();
        if (resolved.startsWith(checkout)) {
            throw new IllegalArgumentException("Raw output must be outside the repository checkout.");
        }
    }

    private static final class Arguments {
        final Path outputDirectory;
        final Path cacheDirectory;
        final String timeframe;
        final String side;

        private Arguments(Path outputDirectory, Path cacheDirectory, String timeframe, String side) {
            this.outputDirectory = outputDirectory.toAbsolutePath().normalize();
            this.cacheDirectory = cacheDirectory.toAbsolutePath().normalize();
            this.timeframe = timeframe;
            this.side = side;
        }

        static Arguments parse(String[] args) {
            Map<String, String> values = new LinkedHashMap<>();
            if (args.length != 8) {
                throw new IllegalArgumentException("Only --output-dir, --cache-dir, --timeframe and --side are accepted.");
            }
            for (int index = 0; index < args.length; index += 2) {
                if (values.put(args[index], args[index + 1]) != null) {
                    throw new IllegalArgumentException("Duplicate argument: " + args[index]);
                }
            }
            Set<String> expected = new LinkedHashSet<>();
            Collections.addAll(expected, "--output-dir", "--cache-dir", "--timeframe", "--side");
            if (!values.keySet().equals(expected)) {
                throw new IllegalArgumentException("Unexpected argument set.");
            }
            String timeframe = values.get("--timeframe").toUpperCase(Locale.ROOT);
            String side = values.get("--side").toLowerCase(Locale.ROOT);
            if (!(timeframe.equals("M15") || timeframe.equals("H1"))) {
                throw new IllegalArgumentException("Timeframe must be M15 or H1.");
            }
            if (!(side.equals("bid") || side.equals("ask"))) {
                throw new IllegalArgumentException("Side must be bid or ask.");
            }
            return new Arguments(
                    Paths.get(values.get("--output-dir")),
                    Paths.get(values.get("--cache-dir")),
                    timeframe,
                    side);
        }
    }

    private static final class BarWriterStrategy implements IStrategy {
        private final Path outputDirectory;
        private final String timeframe;
        private final Period period;
        private final OfferSide side;
        private final long start;
        private final long endExclusive;
        private final Map<Instrument, BufferedWriter> writers = new LinkedHashMap<>();
        private final Map<Instrument, Long> rows = new LinkedHashMap<>();
        private volatile Throwable failure;

        BarWriterStrategy(Path outputDirectory, String timeframe, Period period, OfferSide side,
                          long start, long endExclusive) {
            this.outputDirectory = outputDirectory;
            this.timeframe = timeframe;
            this.period = period;
            this.side = side;
            this.start = start;
            this.endExclusive = endExclusive;
        }

        @Override public void onStart(IContext context) throws JFException {
            try {
                for (Map.Entry<String, String> entry : SYMBOLS.entrySet()) {
                    Instrument instrument = Instrument.fromString(entry.getValue());
                    Path path = outputDirectory.resolve(
                            entry.getKey() + "_" + timeframe + "_" + side.toString().toLowerCase(Locale.ROOT) + ".csv");
                    BufferedWriter writer = Files.newBufferedWriter(
                            path,
                            StandardCharsets.UTF_8,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE);
                    writer.write("timestamp,open,high,low,close,volume\n");
                    writers.put(instrument, writer);
                    rows.put(instrument, 0L);
                }
            } catch (IOException error) {
                failure = error;
                throw new JFException("Cannot create canonical CSV files.");
            }
        }

        @Override public void onBar(Instrument instrument, Period receivedPeriod, IBar askBar, IBar bidBar)
                throws JFException {
            if (!period.equals(receivedPeriod) || !writers.containsKey(instrument)) {
                return;
            }
            IBar bar = side == OfferSide.BID ? bidBar : askBar;
            long timestamp = bar.getTime();
            if (timestamp < start || timestamp >= endExclusive) {
                failure = new IllegalStateException("JForex returned a bar outside the frozen interval.");
                throw new JFException("Boundary violation; acquisition stopped.");
            }
            try {
                BufferedWriter writer = writers.get(instrument);
                writer.write(String.format(
                        Locale.ROOT,
                        "%s,%.10f,%.10f,%.10f,%.10f,%.10f%n",
                        ISO.format(Instant.ofEpochMilli(timestamp)),
                        bar.getOpen(), bar.getHigh(), bar.getLow(), bar.getClose(), bar.getVolume()));
                rows.put(instrument, rows.get(instrument) + 1L);
            } catch (IOException error) {
                failure = error;
                throw new JFException("Cannot write canonical CSV row.");
            }
        }

        @Override public void onStop() throws JFException {
            IOException closeFailure = null;
            for (BufferedWriter writer : writers.values()) {
                try {
                    writer.close();
                } catch (IOException error) {
                    closeFailure = error;
                }
            }
            if (closeFailure != null) {
                failure = closeFailure;
                throw new JFException("Cannot close canonical CSV files.");
            }
        }

        void assertSuccessful() {
            if (failure != null) {
                throw new IllegalStateException("JForex acquisition strategy failed.", failure);
            }
            for (Map.Entry<Instrument, Long> entry : rows.entrySet()) {
                if (entry.getValue() == 0L) {
                    throw new IllegalStateException("Empty JForex series for " + entry.getKey());
                }
            }
        }

        @Override public void onTick(Instrument instrument, ITick tick) {}
        @Override public void onMessage(IMessage message) {}
        @Override public void onAccount(IAccount account) {}
    }
}
