package pipeline;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import utils.StringUtils;

public class PercolatorOutputToPepXML {
   private static final Pattern pattern = Pattern.compile("(.+spectrum=\".+\\.)([0-9]+)\\.([0-9]+)(\\.[0-9]+\".+)");
   private static final Pattern pattern1 = Pattern.compile("base_name=\"([^\"]+)\"");
   private static final Pattern pattern2 = Pattern.compile("raw_data_type=\"([^\"]+)\"");
   private static final Pattern pattern3 = Pattern.compile("raw_data=\"([^\"]+)\"");

   public static void main(String[] args) {
      Locale.setDefault(Locale.US);
      if (args.length == 0) {
         percolatorToPepXML(Paths.get("G:\\dev\\msfragger\\dev2\\5ngHeLaosmoothCE20-52lowguessSRIG450easy4_30t_C2_01_3451.pin"), "G:\\dev\\msfragger\\dev2\\5ngHeLaosmoothCE20-52lowguessSRIG450easy4_30t_C2_01_3451", Paths.get("G:\\dev\\msfragger\\dev2\\5ngHeLaosmoothCE20-52lowguessSRIG450easy4_30t_C2_01_3451_percolator_target_psms.tsv"), Paths.get("G:\\dev\\msfragger\\dev2\\5ngHeLaosmoothCE20-52lowguessSRIG450easy4_30t_C2_01_3451_percolator_decoy_psms.tsv"), Paths.get("G:\\dev\\msfragger\\dev2\\interact-5ngHeLaosmoothCE20-52lowguessSRIG450easy4_30t_C2_01_3451_2"), "DDA", (double)0.0F, "");
      } else if (Files.exists(Paths.get(args[0].replace(".pin", "_edited.pin")), new LinkOption[0])) {
         percolatorToPepXML(Paths.get(args[0].replace(".pin", "_edited.pin")), args[1], Paths.get(args[2]), Paths.get(args[3]), Paths.get(args[4]), args[5], Double.parseDouble(args[6]), args[7].trim());
      } else {
         percolatorToPepXML(Paths.get(args[0]), args[1], Paths.get(args[2]), Paths.get(args[3]), Paths.get(args[4]), args[5], Double.parseDouble(args[6]), args[7].trim());
      }

   }

   private static String getSpectrum(String line) {
      String spectrum = null;

      for(String e : line.split("\\s")) {
         if (e.startsWith("spectrum=")) {
            spectrum = e.substring("spectrum=\"".length(), e.length() - 1);
            break;
         }
      }

      return spectrum.substring(0, spectrum.lastIndexOf("."));
   }

   private static String paddingZeros(String line) {
      Matcher matcher = pattern.matcher(line);
      if (!matcher.matches()) {
         throw new RuntimeException("Cannot parse line " + line);
      } else if (!matcher.group(2).contentEquals(matcher.group(3))) {
         throw new RuntimeException("Cannot parse spectrum ID from  " + line);
      } else {
         String scanNum = matcher.group(2);
         if (scanNum.length() >= 5) {
            return line;
         } else {
            StringBuilder sb = new StringBuilder(5);

            for(int i = 0; i < 5 - scanNum.length(); ++i) {
               sb.append("0");
            }

            sb.append(scanNum);
            String var10000 = matcher.group(1);
            return var10000 + String.valueOf(sb) + "." + String.valueOf(sb) + matcher.group(4);
         }
      }
   }

   private static Spectrum_rank get_spectrum_rank(String s) {
      String charge_rank = s.substring(s.lastIndexOf("."));
      int rank = Integer.parseInt(charge_rank.split("_")[1]);
      return new Spectrum_rank(s.substring(0, s.lastIndexOf(".")), rank);
   }

   private static int get_max_rank(String basename, boolean is_DIA) {
      Path pathDIA = Paths.get(basename + "_rank1.pepXML");
      Path pathDDA = Paths.get(basename + ".pepXML");
      Path path = is_DIA ? pathDIA : pathDDA;
      Pattern compile = Pattern.compile("<parameter name=\"output_report_topN\" value=\"(\\d+)\"/>");

      try {
         BufferedReader br;
         label59: {
            br = Files.newBufferedReader(path);

            int var9;
            try {
               while(true) {
                  String line;
                  if ((line = br.readLine()) == null) {
                     break label59;
                  }

                  Matcher matcher = compile.matcher(line.trim());
                  if (matcher.find()) {
                     var9 = Integer.parseInt(matcher.group(1));
                     break;
                  }
               }
            } catch (Throwable var11) {
               if (br != null) {
                  try {
                     br.close();
                  } catch (Throwable var10) {
                     var11.addSuppressed(var10);
                  }
               }

               throw var11;
            }

            if (br != null) {
               br.close();
            }

            return var9;
         }

         if (br != null) {
            br.close();
         }
      } catch (IOException var12) {
         System.err.println("Cannot find output_report_topN parameter from " + String.valueOf(path.toAbsolutePath()));
         System.exit(1);
         return -1;
      }

      System.err.println("Cannot find output_report_topN parameter from " + String.valueOf(path.toAbsolutePath()));
      System.exit(1);
      return -1;
   }

   private static StringBuilder handle_search_hit(List<String> searchHit, NttNmc nttNmc, PepScore pepScore, int oldRank, int newRank) {
      if (nttNmc != null && pepScore != null) {
         StringBuilder sb = new StringBuilder();
         double calc_neutral_pep_mass = Double.NaN;
         double massdiff = Double.NaN;
         int isomassd = 0;
         Iterator<String> iterator = searchHit.iterator();
         String search_hit_line = (String)iterator.next();

         for(String e : search_hit_line.split("\\s")) {
            if (e.startsWith("massdiff=")) {
               massdiff = Double.parseDouble(e.substring("massdiff=\"".length(), e.length() - 1));
            }

            if (e.startsWith("calc_neutral_pep_mass=")) {
               calc_neutral_pep_mass = Double.parseDouble(e.substring("calc_neutral_pep_mass=\"".length(), e.length() - 1));
            }
         }

         double gap = Double.MAX_VALUE;

         for(int isotope = -6; isotope < 7; ++isotope) {
            if (Math.abs(massdiff - (double)isotope * 1.0033548378) < gap) {
               gap = Math.abs(massdiff - (double)isotope * 1.0033548378);
               isomassd = isotope;
            }
         }

         if (gap > 0.1) {
            isomassd = 0;
         }

         sb.append(oldRank == newRank ? search_hit_line : search_hit_line.replace("hit_rank=\"" + oldRank + "\"", "hit_rank=\"" + newRank + "\"")).append("\n");

         String line;
         while(!(line = (String)iterator.next()).trim().contentEquals("</search_hit>")) {
            sb.append(line).append("\n");
         }

         if (!Float.isNaN(nttNmc.spectralSimilarity)) {
            sb.append(String.format("<search_score name=\"spectralsim\" value=\"%f\"/>\n", nttNmc.spectralSimilarity));
         }

         if (!Float.isNaN(nttNmc.RTscore)) {
            sb.append(String.format("<search_score name=\"rtscore\" value=\"%f\"/>\n", nttNmc.RTscore));
         }

         if (!Float.isNaN(nttNmc.IMscore)) {
            sb.append(String.format("<search_score name=\"imscore\" value=\"%f\"/>\n", nttNmc.IMscore));
         }

         sb.append(String.format("<analysis_result analysis=\"peptideprophet\">\n<peptideprophet_result probability=\"%f\" all_ntt_prob=\"(%f,%f,%f)\">\n<search_score_summary>\n<parameter name=\"fval\" value=\"%f\"/>\n<parameter name=\"ntt\" value=\"%d\"/>\n<parameter name=\"nmc\" value=\"%d\"/>\n<parameter name=\"massd\" value=\"%f\"/>\n<parameter name=\"isomassd\" value=\"%d\"/>\n</search_score_summary>\n</peptideprophet_result>\n</analysis_result>\n", (double)1.0F - pepScore.pep, (double)1.0F - pepScore.pep, (double)1.0F - pepScore.pep, (double)1.0F - pepScore.pep, pepScore.score, nttNmc.ntt, nttNmc.nmc, (massdiff - (double)isomassd * 1.0033548378) * (double)1000000.0F / calc_neutral_pep_mass, isomassd));
         sb.append("</search_hit>\n");
         return sb;
      } else {
         return new StringBuilder();
      }
   }

   private static String handle_spectrum_query(List<String> sq, Map<String, NttNmc[]> pinSpectrumRankNttNmc, Map<String, PepScore[]> pinSpectrumRankPepScore, boolean is_DIA, int DIA_rank) {
      List<List<String>> search_hits = new ArrayList();
      StringBuilder sb = new StringBuilder();
      Iterator<String> iterator = sq.iterator();

      while(iterator.hasNext()) {
         String line = ((String)iterator.next()).trim();
         String spectrum = getSpectrum(line);
         PepScore[] pepScoreArray = (PepScore[])pinSpectrumRankPepScore.get(spectrum);
         if (pepScoreArray == null) {
            return "";
         }

         NttNmc[] nttNmcArray = (NttNmc[])pinSpectrumRankNttNmc.get(spectrum);
         if (nttNmcArray == null) {
            return "";
         }

         if (is_DIA && (nttNmcArray[DIA_rank - 1] == null || pepScoreArray[DIA_rank - 1] == null)) {
            return "";
         }

         sb.append(paddingZeros(line)).append('\n');

         while(iterator.hasNext()) {
            line = ((String)iterator.next()).trim();
            if (line.startsWith("<search_result>")) {
               sb.append(line).append('\n');
            } else if (line.trim().startsWith("<search_hit ")) {
               ArrayList<String> search_hit = new ArrayList();
               search_hit.add(line);

               do {
                  line = (String)iterator.next();
                  search_hit.add(line);
               } while(!line.contentEquals("</search_hit>"));

               search_hits.add(search_hit);
            } else if (!line.trim().startsWith("</search_result>")) {
               if (!line.trim().startsWith("</spectrum_query>")) {
                  throw new IllegalStateException(line);
               }

               sb.append(line).append('\n');
            } else {
               if (is_DIA) {
                  sb.append(handle_search_hit((List)search_hits.get(0), nttNmcArray[DIA_rank - 1], pepScoreArray[DIA_rank - 1], 1, 1));
               } else {
                  TreeMap<Double, Integer> scoreOldRankMinusOne = new TreeMap(Collections.reverseOrder());

                  for(int oldRankMinusOne = 0; oldRankMinusOne < pepScoreArray.length; ++oldRankMinusOne) {
                     PepScore pepScore = pepScoreArray[oldRankMinusOne];
                     if (pepScore != null) {
                        scoreOldRankMinusOne.put(pepScore.score, oldRankMinusOne);
                     }
                  }

                  int newRank = 0;

                  for(Map.Entry<Double, Integer> entry : scoreOldRankMinusOne.entrySet()) {
                     int oldRankMinusOne = (Integer)entry.getValue();
                     List var10001 = (List)search_hits.get(oldRankMinusOne);
                     NttNmc var10002 = nttNmcArray[oldRankMinusOne];
                     PepScore var10003 = pepScoreArray[oldRankMinusOne];
                     int var10004 = oldRankMinusOne + 1;
                     ++newRank;
                     sb.append(handle_search_hit(var10001, var10002, var10003, var10004, newRank));
                  }
               }

               sb.append(line).append('\n');
            }
         }
      }

      return sb.toString();
   }

   public static void percolatorToPepXML(Path pin, String basename, Path percolatorTargetPsms, Path percolatorDecoyPsms, Path outBasename, String DIA_DDA, double minProb, String lcmsPath) {
      if (!Files.exists(Paths.get(lcmsPath), new LinkOption[0])) {
         boolean notOk = true;
         if (lcmsPath.toLowerCase().endsWith("_calibrated.mzml")) {
            String var10000 = lcmsPath.substring(0, lcmsPath.length() - "_calibrated.mzml".length());
            String ss = var10000 + ".mzML";
            if (Files.exists(Paths.get(ss), new LinkOption[0])) {
               lcmsPath = ss;
               notOk = false;
            } else {
               var10000 = lcmsPath.substring(0, lcmsPath.length() - "_calibrated.mzml".length());
               ss = var10000 + "_uncalibrated.mzML";
               if (Files.exists(Paths.get(ss), new LinkOption[0])) {
                  lcmsPath = ss;
                  notOk = false;
               }
            }
         } else if (lcmsPath.toLowerCase().endsWith("_uncalibrated.mzml")) {
            String var83 = lcmsPath.substring(0, lcmsPath.length() - "_uncalibrated.mzml".length());
            String ss = var83 + ".mzML";
            if (Files.exists(Paths.get(ss), new LinkOption[0])) {
               lcmsPath = ss;
               notOk = false;
            } else {
               var83 = lcmsPath.substring(0, lcmsPath.length() - "_uncalibrated.mzml".length());
               ss = var83 + "_calibrated.mzML";
               if (Files.exists(Paths.get(ss), new LinkOption[0])) {
                  lcmsPath = ss;
                  notOk = false;
               }
            }
         }

         if (notOk) {
            System.err.printf(lcmsPath + " does not exist.");
            System.exit(1);
         }
      }

      boolean is_DIA = DIA_DDA.equals("DIA");
      int max_rank = get_max_rank(basename, is_DIA);
      if (max_rank < 1) {
         System.err.println("Cannot find output_report_topN parameter from " + basename + "'s pepXML file.");
         System.exit(1);
      }

      Map<String, NttNmc[]> pinSpectrumRankNttNmc = new HashMap();
      Map<String, PepScore[]> pinSpectrumRankPepScore = new HashMap();

      try {
         BufferedReader brtsv = Files.newBufferedReader(pin);
         String pin_header = brtsv.readLine();
         if (pin_header == null) {
            throw new NullPointerException("Could not read the first line of " + String.valueOf(pin.toAbsolutePath()) + ".");
         }

         List<String> colnames = Arrays.asList(pin_header.split("\t"));
         int indexOf_SpecId = colnames.indexOf("SpecId");
         int indexOf_ntt = colnames.indexOf("ntt");
         int indexOf_nmc = colnames.indexOf("nmc");
         int indexOf_spectralSimilarity = -1;
         int indexOf_RTscore = -1;
         int indexOf_IMscore = -1;
         if (colnames.contains("bray_curtis")) {
            indexOf_spectralSimilarity = colnames.indexOf("bray_curtis");
         }

         if (colnames.contains("unweighted_spectral_entropy")) {
            indexOf_spectralSimilarity = colnames.indexOf("unweighted_spectral_entropy");
         }

         if (colnames.contains("delta_RT_loess_real")) {
            indexOf_RTscore = colnames.indexOf("delta_RT_loess_real");
         }

         if (colnames.contains("delta_IM_loess")) {
            indexOf_IMscore = colnames.indexOf("delta_IM_loess");
         }

         String line;
         String specId;
         int rank;
         int ntt;
         int nmc;
         float spectralSimilarity;
         float RTscore;
         float IMscore;
         for(; (line = brtsv.readLine()) != null; ((NttNmc[])pinSpectrumRankNttNmc.computeIfAbsent(specId, (ex) -> new NttNmc[max_rank]))[rank - 1] = new NttNmc(ntt, nmc, spectralSimilarity, RTscore, IMscore)) {
            String[] split = line.split("\t");
            String raw_SpecId = split[indexOf_SpecId];
            Spectrum_rank spectrum_rank = get_spectrum_rank(raw_SpecId);
            specId = spectrum_rank.spectrum;
            rank = spectrum_rank.rank;
            ntt = Integer.parseInt(split[indexOf_ntt]);
            nmc = Integer.parseInt(split[indexOf_nmc]);
            spectralSimilarity = Float.NaN;
            if (indexOf_spectralSimilarity != -1) {
               spectralSimilarity = Float.parseFloat(split[indexOf_spectralSimilarity]);
            }

            RTscore = Float.NaN;
            if (indexOf_RTscore != -1) {
               RTscore = Float.parseFloat(split[indexOf_RTscore]);
            }

            IMscore = Float.NaN;
            if (indexOf_IMscore != -1) {
               IMscore = Float.parseFloat(split[indexOf_IMscore]);
            }
         }
      } catch (IOException e) {
         throw new UncheckedIOException(e);
      }

      for(Path tsv : new Path[]{percolatorTargetPsms, percolatorDecoyPsms}) {
         try {
            BufferedReader brtsv = Files.newBufferedReader(tsv);

            try {
               String percolator_header = brtsv.readLine();
               List<String> colnames = Arrays.asList(percolator_header.split("\t"));
               int indexOfPSMId = colnames.indexOf("PSMId");
               int indexOfPEP = colnames.indexOf("posterior_error_prob");
               int indexOfScore = colnames.indexOf("score");

               String line;
               while((line = brtsv.readLine()) != null) {
                  String[] split = line.split("\t");
                  String raw_psmid = split[indexOfPSMId];
                  Spectrum_rank spectrum_rank = get_spectrum_rank(raw_psmid);
                  String specId = spectrum_rank.spectrum;
                  int rank = spectrum_rank.rank;

                  double pep;
                  try {
                     pep = Double.parseDouble(split[indexOfPEP]);
                  } catch (NumberFormatException var38) {
                     pep = (double)1.0F;
                  }

                  if (!((double)1.0F - pep < minProb)) {
                     double score;
                     try {
                        score = Double.parseDouble(split[indexOfScore]);
                     } catch (NumberFormatException var37) {
                        score = (double)0.0F;
                     }

                     ((PepScore[])pinSpectrumRankPepScore.computeIfAbsent(specId, (ex) -> new PepScore[max_rank]))[rank - 1] = new PepScore(pep, score);
                  }
               }
            } catch (Throwable var42) {
               if (brtsv != null) {
                  try {
                     brtsv.close();
                  } catch (Throwable var36) {
                     var42.addSuppressed(var36);
                  }
               }

               throw var42;
            }

            if (brtsv != null) {
               brtsv.close();
            }
         } catch (IOException e) {
            throw new UncheckedIOException(e);
         }
      }

      for(int rank = 1; rank <= (is_DIA ? max_rank : 1); ++rank) {
         Path output_rank = is_DIA ? Paths.get(String.valueOf(outBasename) + "_rank" + rank + ".pep.xml") : Paths.get(String.valueOf(outBasename) + ".pep.xml");
         Path pepxml_rank = is_DIA ? Paths.get(basename + "_rank" + rank + ".pepXML") : Paths.get(basename + ".pepXML");

         try {
            BufferedReader brpepxml = Files.newBufferedReader(pepxml_rank);

            try {
               BufferedWriter out = Files.newBufferedWriter(output_rank);

               try {
                  String line;
                  while((line = brpepxml.readLine()) != null) {
                     if (line.trim().startsWith("<msms_run_summary")) {
                        Matcher matcher1 = pattern1.matcher(line);
                        if (matcher1.find()) {
                           line = matcher1.replaceFirst(Matcher.quoteReplacement("base_name=\"" + StringUtils.upToLastDot(lcmsPath) + "\""));
                           Matcher matcher2 = pattern2.matcher(line);
                           if (matcher2.find()) {
                              line = matcher2.replaceFirst("raw_data_type=\"" + StringUtils.afterLastDot(lcmsPath) + "\"");
                           }

                           Matcher matcher3 = pattern3.matcher(line);
                           if (matcher3.find()) {
                              line = matcher3.replaceFirst("raw_data=\"" + StringUtils.afterLastDot(lcmsPath) + "\"");
                           }
                        } else {
                           System.err.printf("Could not find the base_name from " + String.valueOf(pepxml_rank));
                           System.exit(1);
                        }
                     }

                     out.write(line + "\n");
                     if (line.trim().startsWith("<msms_pipeline_analysis ")) {
                        String now = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss").format(LocalDateTime.now());
                        String tmp = String.format("<analysis_summary analysis=\"Percolator\" time=\"%s\">\n<peptideprophet_summary min_prob=\"%.2f\">\n<inputfile name=\"%s\"/>\n</peptideprophet_summary>\n</analysis_summary>\n<analysis_summary analysis=\"database_refresh\" time=\"%s\"/>\n<analysis_summary analysis=\"interact\" time=\"%s\">\n<interact_summary filename=\"%s\" directory=\"\">\n<inputfile name=\"%s\"/>\n</interact_summary>\n</analysis_summary>\n<dataset_derivation generation_no=\"0\"/>\n", now, minProb, pepxml_rank.toAbsolutePath(), now, now, output_rank.toAbsolutePath(), pepxml_rank.toAbsolutePath());
                        out.write(tmp);
                     }

                     if (line.trim().equals("</search_summary>")) {
                        break;
                     }
                  }

                  while((line = brpepxml.readLine()) != null) {
                     if (line.trim().startsWith("<spectrum_query")) {
                        List<String> sq = new ArrayList();
                        sq.add(line);

                        while((line = brpepxml.readLine()) != null) {
                           sq.add(line);
                           if (line.trim().equals("</spectrum_query>")) {
                              out.write(handle_spectrum_query(sq, pinSpectrumRankNttNmc, pinSpectrumRankPepScore, is_DIA, rank));
                              break;
                           }
                        }
                     }
                  }

                  out.write("</msms_run_summary>\n</msms_pipeline_analysis>");
               } catch (Throwable var39) {
                  if (out != null) {
                     try {
                        out.close();
                     } catch (Throwable var35) {
                        var39.addSuppressed(var35);
                     }
                  }

                  throw var39;
               }

               if (out != null) {
                  out.close();
               }
            } catch (Throwable var40) {
               if (brpepxml != null) {
                  try {
                     brpepxml.close();
                  } catch (Throwable var34) {
                     var40.addSuppressed(var34);
                  }
               }

               throw var40;
            }

            if (brpepxml != null) {
               brpepxml.close();
            }
         } catch (IOException e) {
            throw new UncheckedIOException(e);
         }
      }

   }

   private static class Spectrum_rank {
      final String spectrum;
      final int rank;

      Spectrum_rank(String spectrum, int rank) {
         this.spectrum = spectrum;
         this.rank = rank;
      }
   }

   static class NttNmc {
      final int ntt;
      final int nmc;
      final float spectralSimilarity;
      final float RTscore;
      final float IMscore;

      public NttNmc(int ntt, int nmc, float spectralSimilarity, float RTscore, float IMscore) {
         this.ntt = ntt;
         this.nmc = nmc;
         this.spectralSimilarity = spectralSimilarity;
         this.RTscore = RTscore;
         this.IMscore = IMscore;
      }
   }

   static class PepScore {
      final double pep;
      final double score;

      public PepScore(double pep, double score) {
         this.pep = pep;
         this.score = score;
      }
   }
}
