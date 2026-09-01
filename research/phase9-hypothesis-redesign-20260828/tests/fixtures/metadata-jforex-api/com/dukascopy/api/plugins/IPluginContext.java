package com.dukascopy.api.plugins;

import com.dukascopy.api.IContext;

public interface IPluginContext extends IContext {
    void stop();
}
