package com.dukascopy.api.plugins;

import com.dukascopy.api.JFException;

public abstract class Plugin {
    public void onStart(IPluginContext context) throws JFException {}
    public void onStop() throws JFException {}
}
