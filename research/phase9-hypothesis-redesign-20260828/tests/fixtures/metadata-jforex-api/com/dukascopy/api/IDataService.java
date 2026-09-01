package com.dukascopy.api;

import java.util.Set;

public interface IDataService {
    Set<ITimeDomain> getOfflineTimeDomains(long from, long to, Instrument instrument) throws JFException;
}
