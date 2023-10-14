import os
import sys

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

import numpy
import scipy
import pyqtgraph as pg

from signal_processing import open_csv_file, open_data_frame, tfa
from interface import Ui_MainWindow


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.showMaximized()

        # File menu
        self.menu_file_open_action.setShortcut("Ctrl+O")
        self.menu_file_open_action.triggered.connect(self.open_file)

        # Combo boxes
        self.topAxesComboBox.currentIndexChanged.connect(self.change_top_axes)
        self.bottomAxesComboBox.currentIndexChanged.connect(self.change_bottom_axes)

        # Init last opened directory
        self.last_dir = "."
        self.file_name = ""

        # Init plot config variables
        self.top_roi = None
        self.bottom_roi = None
        self._roi_region = None

    @property
    def duration(self):
        if self.time is not None:
            return self.time[-1]
        else:
            return None

    @property
    def start_signal(self):
        if self.time is not None:
            return self.time[0]
        else:
            return None

    @property
    def vlf_range(self):
        return float(self.lineEditVLFLower.text()), float(self.lineEditVLFUpper.text())

    @property
    def lf_range(self):
        return float(self.lineEditLFLower.text()), float(self.lineEditLFUpper.text())

    @property
    def hf_range(self):
        return float(self.lineEditHFLower.text()), float(self.lineEditHFUpper.text())

    @property
    def roi_region(self):
        if self._roi_region is None:
            return [0, self.duration]
        else:
            return self._roi_region

    def _save_last_dir(self, file_name):
        self.last_dir = os.path.dirname(file_name)

    def _set_file_name(self, file_path):
        file_name = os.path.basename(file_path)
        self.lineEditFileName.setText(file_name)

    def _update_edit_time_ranges(self, region):
        self.lineEditStartTimeAxes.setText(f"{region[0]:.2f}")
        self.lineEditEndTimeAxes.setText(f"{region[1]:.2f}")

    def open_file(self):
        self.file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select file",
            self.last_dir,
            "CSV files (*.txt)"
        )
        if self.file_path:
            self._save_last_dir(self.file_path)
            # self.time, self.cbv, self.abp = open_csv_file(self.file_name)
            self.time, self.abp, self.cbfv = open_data_frame(self.file_path)
            self._set_file_name(self.file_path)

            self.plot_cbfv(self.top_axes)
            self.plot_abp(self.bottom_axes)
            self._update_edit_time_ranges(region=(0, self.duration))

            # Signal Processing
            # TODO: get config from panel
            fs = 10.0
            self.results = tfa(self.abp, self.cbfv, fs)

    def change_top_axes(self):
        {
            0: self.plot_cbfv,
            1: self.plot_cbfv_psd,
            2: self.plot_gain,
            3: self.plot_coherence,
            4: self.plot_phase,
        }.get(self.topAxesComboBox.currentIndex(), lambda: None)(self.top_axes)

    def change_bottom_axes(self):
        {
            0: self.plot_abp,
            1: self.plot_abp_psd,
            2: self.plot_gain,
            3: self.plot_coherence,
            4: self.plot_phase,
        }.get(self.bottomAxesComboBox.currentIndex(), lambda: None)(self.bottom_axes)

    def update_top_roi(self):
        # Do not let area outside signal
        region = self.top_roi.getRegion()
        self._roi_region = region
        if self.bottom_roi is not None:
            self.bottom_roi.setRegion(region)

        self._update_edit_time_ranges(region)

    def update_bottom_roi(self):
        # Do not let area outside signal
        region = self.bottom_roi.getRegion()
        self._roi_region = region
        if self.top_roi is not None:
            self.top_roi.setRegion(region)

        self._update_edit_time_ranges(region)

    def add_roi(self, axes, action):
        roi = pg.LinearRegionItem(self.roi_region, pen=pg.mkPen(width=3.5))
        roi.setZValue(-10)

        # Callback when area change.
        roi.sigRegionChanged.connect(action)
        axes.addItem(roi)
        return roi

    def plot_cbfv(self, axes):
        self.plot_time_series(
            axes,
            self.time,
            self.cbfv,
            xlabel="Time (s)",
            ylabel="CBFV (cm/s)",
            xlim=[0, self.duration],
            color="g"
        )
        self.top_roi = self.add_roi(self.top_axes, self.update_top_roi)

    def plot_cbfv_psd(self, axes):
        self.plot_psd(
            axes,
            self.results["frequency"],
            self.results["pyy"],  # TODO: change pyy to cbfv_psd
            vlf=self.vlf_range,
            lf=self.lf_range,
            hf=self.hf_range,
        )

    def plot_abp(self, axes):
        self.plot_time_series(
            axes,
            self.time,
            self.abp,
            xlabel="Time (s)",
            ylabel="ABP (mmHg)",
            xlim=[0, self.duration],
            color="y"
        )
        self.bottom_roi = self.add_roi(self.bottom_axes, self.update_bottom_roi)

    def plot_abp_psd(self, axes):
        self.plot_psd(
            axes,
            self.results["frequency"],
            self.results["pxx"],  # TODO: change pxx to abp_psd
            vlf=self.vlf_range,
            lf=self.lf_range,
            hf=self.hf_range,
        )

    def plot_gain(self, axes):
        freq = self.results["frequency"]
        self.plot_time_series(
            axes,
            freq,
            self.results["gain"],
            xlabel="Frequency (Hz)",
            ylabel="gain",
            xlim=[0, self.hf_range[1]],
            color="g"
        )
        self._add_frequency_bands_lines(axes)

    def plot_coherence(self, axes):
        freq = self.results["frequency"]
        self.plot_time_series(
            axes,
            freq,
            self.results["coherence"],
            xlabel="Frequency (Hz)",
            ylabel="Coherence",
            xlim=[0, self.hf_range[1]],
            color="g"
        )
        self._add_frequency_bands_lines(axes)
        # Add coherence threshold line
        threshold = self.results.get("coherence_threshold", None)
        axes.addLine(
            x=None,
            y=threshold,
            pen=pg.mkPen("r", width=2)
        )

    def plot_phase(self, axes):
        freq = self.results["frequency"]
        self.plot_time_series(
            axes,
            freq,
            self.results["phase"],
            xlabel="Frequency (Hz)",
            ylabel="Phase",
            xlim=[0, self.hf_range[1]],
            color="g"
        )
        self._add_frequency_bands_lines(axes)

    def plot_time_series(self, axes, time, signal, xlabel, ylabel, xlim, color):
        axes.clear()
        axes.plot(time, signal, pen=pg.mkPen(color,  width=2))
        axes.setLabel("left", ylabel)
        axes.setLabel("bottom", xlabel)
        axes.showGrid(x=True, y=True, alpha=1.0)
        axes.setRange(xRange=xlim)

    def _add_frequency_line(self, axes, x, ylim):
        axes.addLine(
            x=x,
            y=ylim,
            pen=pg.mkPen("w", width=2, dash=[2, 4])
        )

    def _add_frequency_bands_lines(self, axes):
        ylim = axes.getAxis("left").range
        self._add_frequency_line(axes, x=[self.vlf_range[0], self.vlf_range[0]], ylim=ylim)
        self._add_frequency_line(axes, x=[self.vlf_range[1], self.vlf_range[1]], ylim=ylim)
        self._add_frequency_line(axes, x=[self.lf_range[0], self.lf_range[0]], ylim=ylim)
        self._add_frequency_line(axes, x=[self.lf_range[1], self.lf_range[1]], ylim=ylim)
        self._add_frequency_line(axes, x=[self.hf_range[0], self.hf_range[0]], ylim=ylim)
        self._add_frequency_line(axes, x=[self.hf_range[1], self.hf_range[1]], ylim=ylim)

    def plot_psd(self, axes, frequency, psd, vlf, lf, hf):
        # For aesthetic purpose, we are interpolating and resampling the PSD
        # for increased visual frequency resolution
        interp_frequency = numpy.arange(frequency[0], frequency[-1], 1 / 10000.0)
        cs = scipy.interpolate.CubicSpline(frequency, psd)
        interp_psd = cs(interp_frequency)

        indexes_vlf = numpy.where(
            numpy.logical_and(interp_frequency >= vlf[0], interp_frequency < vlf[1])
        )[0]
        indexes_lf = numpy.where(numpy.logical_and(
            interp_frequency >= lf[0], interp_frequency < lf[1])
        )[0]
        indexes_hf = numpy.where(
            numpy.logical_and(interp_frequency >= hf[0], interp_frequency < hf[1])
        )[0]

        axes.clear()
        # Total PSD
        axes.plot(
            interp_frequency,
            interp_psd,
            fillLevel=0.0,
            brush=(127, 127, 127, 100)
        )
        # VLF
        axes.plot(
            interp_frequency[indexes_vlf],
            interp_psd[indexes_vlf],
            fillLevel=0.0,
            brush=(127, 127, 255, 200)
        )
        # LF
        axes.plot(
            interp_frequency[indexes_lf],
            interp_psd[indexes_lf],
            fillLevel=0.0,
            brush=(178, 127, 255, 200)
        )
        # HF
        axes.plot(
            interp_frequency[indexes_hf],
            interp_psd[indexes_hf],
            fillLevel=0.0,
            brush=(127, 127, 255, 200)
        )

        axes.setRange(xRange=[0, 0.5])
        axes.setLabel("left", "PSD (ms²/Hz)")
        axes.setLabel("bottom", "Frequency (Hz)")
        axes.showGrid(x=True, y=True, alpha=1.0)

        # Add frequency band lines
        self._add_frequency_bands_lines(axes)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
