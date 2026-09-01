package com.dukascopy.api.system;

import com.dukascopy.api.IStrategyExceptionHandler;
import com.dukascopy.api.plugins.Plugin;
import java.io.File;
import java.util.UUID;

public interface IClient {
    void setCacheDirectory(File directory);
    void connect(String jnlp, String username, String password) throws Exception;
    boolean isConnected();
    UUID runPlugin(Plugin plugin, IStrategyExceptionHandler handler);
}
