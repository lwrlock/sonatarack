# SonataRack DSP & Audio Engine

Bjorklund dağılımı $E(k,n)$, $n$ not sayısı için $k$-inci notun olasılığını tanımlar; $P_k = \frac{2}{\pi}\sqrt{\frac{k}{n}}$. ADSR'de eksponansiyel yükselen kısım ($A=1$) ve 1-pole filtrede $f_c < f_{sample}/4$ kuralı, sayısal istikrarsızlığı önler. 16-bit PCM exportta `numpy.save()` ile WAV kaydedilir; FFT spektrum binleri `np.fft.rfft` ile hesaplanır. SQLite'te `presets` tablosu (JSON preset) ve `patterns` tablosu (
